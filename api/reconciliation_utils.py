"""
Utility functions for OpenRefine reconciliation API.

This module contains helper functions for processing reconciliation queries,
parsing request data, and formatting responses.
"""

import json
import logging
import time
from typing import Any
from urllib.parse import parse_qs

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from api.constants import BASE_URL, GND_URI_PREFIX
from api.services.properties import handle_extend_request
from api.services.search import get_gnd_record_by_id, search_gnd_batch
from api.vocabularies.base import VocabConfig
from api.vocabularies.gnd import GND_VOCAB
from config import RECONCILIATION_BATCH_SIZE, SERVICE_LOGO_URL, SERVICE_VERSION

logger = logging.getLogger(__name__)


def service_manifest_response(vocab: VocabConfig = GND_VOCAB) -> dict:
    """
    Builds the OpenRefine service manifest response for a vocabulary
    (GND by default).

    This describes the reconciliation service's capabilities to OpenRefine.
    """
    service_base_url = f"{BASE_URL}{vocab.route_prefix}"

    manifest: dict[str, Any] = {
        "versions": ["0.2"],
        "name": vocab.service_name,
        "identifierSpace": vocab.identifier_space,
        "schemaSpace": vocab.schema_space,
        "defaultTypes": list(vocab.types),
        "documentation": f"{BASE_URL}/docs",
        "serviceVersion": SERVICE_VERSION,
        "batchSize": RECONCILIATION_BATCH_SIZE,
        "view": {"url": vocab.view_url_template},
        "preview": {
            "url": f"{service_base_url}/preview/{{{{id}}}}",
            "width": 430,
            "height": 300,
        },
        "suggest": {
            "entity": {"service_url": service_base_url, "service_path": "/suggest/entity"},
            "type": {"service_url": service_base_url, "service_path": "/suggest/type"},
            "property": {
                "service_url": service_base_url,
                "service_path": "/suggest/property",
            },
        },
        "extend": {
            "propose_properties": {
                "service_url": service_base_url,
                "service_path": "/properties",
            },
            "property_settings": [
                {
                    "name": "limit",
                    "label": "Limit",
                    "type": "number",
                    "default": 0,
                    "help_text": "Maximum number of values to return per row. Use 0 for no limit.",
                },
                {
                    "name": "content",
                    "label": "Content",
                    "type": "select",
                    "default": "literal",
                    "help_text": "Return either identifiers/URIs or readable literal labels.",
                    "choices": [
                        {"value": "id", "name": "ID"},
                        {"value": "literal", "name": "Literal"},
                    ],
                },
            ],
        },
    }

    # `logo` is optional and only meaningful if an actual square image is
    # available, so it is omitted unless configured.
    if SERVICE_LOGO_URL:
        manifest["logo"] = SERVICE_LOGO_URL

    return manifest


def handle_reconciliation_queries(
    queries: dict,
    limit: int = 5,
    vocab: VocabConfig = GND_VOCAB,
) -> dict:
    """
    Processes OpenRefine-style batched reconciliation queries.

    All queries in the batch are sent to OpenSearch in a single `_msearch`
    request (instead of one `search()` call per query), which is what makes
    large OpenRefine batches (e.g. 40k+ rows processed 50 at a time) fast.

    Args:
        queries: Dictionary of query ID to query object
        limit: Maximum results per query

    Returns:
        Dictionary mapping query IDs to result objects
    """
    batch_start = time.perf_counter()

    # Reconciliation API 0.2: a service MAY reject batches larger than the
    # `batchSize` it advertises in its manifest with HTTP 413.
    if len(queries) > RECONCILIATION_BATCH_SIZE:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Reconciliation query batch of {len(queries)} exceeds the "
                f"advertised batchSize of {RECONCILIATION_BATCH_SIZE}."
            ),
        )

    query_ids: list[str] = []
    query_specs: list[dict[str, Any]] = []
    invalid_query_ids: list[str] = []
    properties_used: set[str] = set()

    for query_id, query_object in queries.items():
        if isinstance(query_object, str):
            query_text = query_object
            entity_type = None
            details: list[dict[str, Any]] = []
            query_limit = limit

        elif isinstance(query_object, dict):
            query_text = query_object.get("query", "")
            entity_type = extract_entity_type(query_object)
            details = extract_reconciliation_properties(query_object)
            query_limit = query_object.get("limit", limit)

        else:
            invalid_query_ids.append(query_id)
            continue

        query_ids.append(query_id)
        query_specs.append(
            {
                "query": query_text,
                "limit": query_limit,
                "entity_type": entity_type,
                "properties": details,
            }
        )

        for detail in details:
            pid = detail.get("pid")

            if pid:
                properties_used.add(str(pid))

    results_per_query, timing = search_gnd_batch(query_specs, vocab=vocab)

    response: dict[str, Any] = {
        query_id: {"result": []} for query_id in invalid_query_ids
    }

    for query_id, results in zip(query_ids, results_per_query):
        response[query_id] = {"result": results}

    total_ms = (time.perf_counter() - batch_start) * 1000

    logger.info(
        "reconciliation batch: batch_size=%d properties=%s total_ms=%.1f "
        "opensearch_ms=%.1f postprocessing_ms=%.1f",
        len(queries),
        sorted(properties_used) if properties_used else "none",
        total_ms,
        timing.get("opensearch_ms", 0.0),
        timing.get("postprocessing_ms", 0.0),
    )

    return response


def extract_entity_type(query_object: dict) -> str | None:
    """
    Extracts the optional reconciliation type from an OpenRefine query object.

    OpenRefine can send type as:
    - "Person"
    - {"id": "Person", "name": "Person"}
    """
    entity_type = query_object.get("type")

    if not entity_type:
        return None

    if isinstance(entity_type, str):
        return entity_type

    if isinstance(entity_type, dict):
        return entity_type.get("id")

    return None


def extract_reconciliation_properties(query_object: dict) -> list:
    """
    Extracts additional reconciliation properties from an OpenRefine query.

    OpenRefine sends details from other columns as:
    {
      "properties": [
        {
          "pid": "dateOfBirth",
          "v": "1749"
        }
      ]
    }
    """
    properties = query_object.get("properties", [])

    if not isinstance(properties, list):
        return []

    cleaned = []

    for prop in properties:
        if not isinstance(prop, dict):
            continue

        prop_id = prop.get("pid") or prop.get("id")
        value = prop.get("v") or prop.get("value")

        if not prop_id or value is None:
            continue

        cleaned.append(
            {
                "pid": str(prop_id),
                "v": value,
            }
        )

    return cleaned


def gnd_uri_to_reconciled_value(value: str) -> dict | None:
    """
    Converts a GND URI into an OpenRefine reconciled value object.

    Example:
    https://d-nb.info/gnd/1008453-8

    becomes:
    {
      "id": "1008453-8",
      "name": "Universität Leipzig",
      "type": [...]
    }
    """
    if not value.startswith(GND_URI_PREFIX):
        return None

    gnd_id = value.replace(GND_URI_PREFIX, "").strip("/")

    if not gnd_id:
        return None

    record = get_gnd_record_by_id(gnd_id)

    if not record:
        return {
            "id": gnd_id,
            "name": gnd_id,
        }

    preferred_name = record.get("preferredName") or gnd_id

    result = {
        "id": gnd_id,
        "name": preferred_name,
    }

    entity_type = record.get("type")

    if entity_type:
        result["type"] = format_entity_types_for_extend(entity_type)

    return result


def format_entity_types_for_extend(entity_types) -> list:
    """
    Converts stored type values into simple OpenRefine type objects.
    """
    if not entity_types:
        return []

    if isinstance(entity_types, str):
        entity_types = [entity_types]

    if not isinstance(entity_types, list):
        return []

    return [
        {
            "id": str(entity_type),
            "name": str(entity_type),
        }
        for entity_type in entity_types
    ]


def should_resolve_gnd_uri(prop_id: str) -> bool:
    """
    Checks if a property value should be resolved from GND URI to name.

    Certain relation properties (like professionOrOccupation) store GND URIs
    that should be resolved to readable names for display.
    """
    return prop_id in {
        "professionOrOccupation",
        "placeOfBirth",
        "placeOfDeath",
        "placeOfActivity",
    }


async def parse_and_handle_root_post(
    request: Request,
    vocab: VocabConfig = GND_VOCAB,
):
    """
    Parses and handles POST requests to the root endpoint.

    Supports both JSON and form-encoded requests.
    Handles both reconciliation queries and data extension requests.
    """
    body_bytes = await request.body()
    body_text = body_bytes.decode("utf-8")

    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        try:
            body_json = json.loads(body_text)
        except json.JSONDecodeError as error:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Invalid JSON body",
                    "details": str(error),
                },
            )

        if "queries" in body_json:
            return handle_reconciliation_queries(
                queries=body_json["queries"],
                limit=5,
                vocab=vocab,
            )

        if "extend" in body_json:
            return handle_extend_request(body_json["extend"], vocab=vocab)

        # Fallback: treat JSON object as a reconciliation batch
        return handle_reconciliation_queries(
            queries=body_json,
            limit=5,
            vocab=vocab,
        )

    parsed_form = parse_qs(body_text)

    if "queries" in parsed_form:
        queries_raw = parsed_form["queries"][0]

        try:
            parsed_queries = json.loads(queries_raw)
        except json.JSONDecodeError as error:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Invalid JSON in 'queries' parameter",
                    "details": str(error),
                },
            )

        return handle_reconciliation_queries(
            queries=parsed_queries,
            limit=5,
            vocab=vocab,
        )

    if "extend" in parsed_form:
        extend_raw = parsed_form["extend"][0]

        try:
            extend_request = json.loads(extend_raw)
        except json.JSONDecodeError as error:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Invalid JSON in 'extend' parameter",
                    "details": str(error),
                },
            )

        return handle_extend_request(extend_request, vocab=vocab)

    return JSONResponse(
        status_code=400,
        content={"error": "Missing 'queries' or 'extend' parameter"},
    )
