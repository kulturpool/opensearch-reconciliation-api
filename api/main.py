import json
from urllib.parse import parse_qs

from fastapi import FastAPI, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from api.services.search import get_gnd_record_by_id, search_gnd
from fastapi.middleware.cors import CORSMiddleware

from html import escape
from api.services.properties import get_property_values_from_record

from api.services.property_labels import property_label

from api.services.properties import (
    get_property_proposals_from_index,
    get_property_values_from_record,
    suggest_properties_from_index,
)

from api.services.property_registry import (
    get_registry_properties_for_type,
    suggest_registry_properties,
)

from fastapi.responses import HTMLResponse
from api.services.preview import render_preview_for_id

from pathlib import Path
from fastapi.responses import JSONResponse
import json

from typing import Any
from fastapi import Body
from json import JSONDecodeError

from api.services.properties import handle_extend_request


from api.models.openapi_models import ExtendRequest, ExtendResponse

from api.models.openapi_models import UpdateStatusResponse


UPDATE_STATE_FILE = Path("data/state/update_state.json")

tags_metadata = [
    {
        "name": "OpenRefine",
        "description": "OpenRefine-compatible reconciliation endpoints.",
    },
    {
        "name": "Suggest",
        "description": "Entity, type and property suggestion endpoints.",
    },
    {
        "name": "Extend",
        "description": "Data extension endpoints for reconciled values.",
    },
    {
        "name": "Preview",
        "description": "HTML preview endpoint for OpenRefine.",
    },
    {
        "name": "Status",
        "description": "Operational status endpoints.",
    },
]

OPENREFINE_POST_OPENAPI_EXTRA: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {
            "application/x-www-form-urlencoded": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "queries": {
                            "type": "string",
                            "description": "JSON object containing OpenRefine reconciliation queries.",
                            "example": '{"q1":{"query":"Goethe","type":"DifferentiatedPerson"}}',
                        },
                        "extend": {
                            "type": "string",
                            "description": "JSON object containing OpenRefine data extension request.",
                            "example": '{"ids":["118540238"],"properties":[{"id":"preferredName"},{"id":"dateOfBirth"}]}',
                        },
                    },
                }
            }
        },
    }
}

OPENAPI_DESCRIPTION = """
Local GND Reconciliation API for OpenRefine.

This service provides:
- OpenRefine-compatible reconciliation
- entity, type and property suggest endpoints
- data extension / Add columns from reconciled values
- preview endpoint
- local GND index backed by OpenSearch
- EntityFacts enrichment
- daily incremental OAI updates
"""

app = FastAPI(
    title="Local GND Reconciliation API",
    summary="Local OpenRefine-compatible reconciliation service for GND.",
    description=OPENAPI_DESCRIPTION,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    contact={
        "name": "Kulturpool",
        "url": "https://kulturpool.at",
    },
    license_info={
        "name": "See repository license and DNB data terms",
    },
    openapi_tags=tags_metadata,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

GND_TYPES = [
    {
        "id": "AuthorityResource",
        "name": "Normdatenressource",
    },
    {
        "id": "CorporateBody",
        "name": "Körperschaft",
        "broader": [
            {
                "id": "AuthorityResource",
                "name": "Normdatenressource",
            }
        ],
    },
    {
        "id": "ConferenceOrEvent",
        "name": "Konferenz oder Veranstaltung",
        "broader": [
            {
                "id": "AuthorityResource",
                "name": "Normdatenressource",
            }
        ],
    },
    {
        "id": "SubjectHeading",
        "name": "Schlagwort",
        "broader": [
            {
                "id": "AuthorityResource",
                "name": "Normdatenressource",
            }
        ],
    },
    {
        "id": "Work",
        "name": "Werk",
        "broader": [
            {
                "id": "AuthorityResource",
                "name": "Normdatenressource",
            }
        ],
    },
    {
        "id": "PlaceOrGeographicName",
        "name": "Geografikum",
        "broader": [
            {
                "id": "AuthorityResource",
                "name": "Normdatenressource",
            }
        ],
    },
    {
        "id": "DifferentiatedPerson",
        "name": "Individualisierte Person",
        "broader": [
            {
                "id": "AuthorityResource",
                "name": "Normdatenressource",
            }
        ],
    },
    {
        "id": "Family",
        "name": "Familie",
        "broader": [
            {
                "id": "AuthorityResource",
                "name": "Normdatenressource",
            }
        ],
    },
]

GND_PROPERTIES = [ # Definition of the GND properties, adapt accordingly!
    {
        "id": "id",
        "name": "GND ID"
    },
    {
        "id": "uri",
        "name": "URI"
    },
    {
        "id": "preferredName",
        "name": "Preferred Name"
    },
    {
        "id": "variantName",
        "name": "Variant Names"
    },
    {
        "id": "type",
        "name": "Entity Type"
    },
    {
        "id": "dateOfBirth",
        "name": "Date of Birth"
    },
    {
        "id": "dateOfDeath",
        "name": "Date of Death"
    },
    {
        "id": "professionOrOccupation",
        "name": "Profession or Occupation"
    },
    {
        "id": "placeOfBirth",
        "name": "Place of Birth"
    },
    {
        "id": "placeOfDeath",
        "name": "Place of Death"
    },
    {
        "id": "source",
        "name": "Source"
    }
]

BASE_URL = "http://127.0.0.1:8083"
GND_URI_PREFIX = "https://d-nb.info/gnd/"


RELATION_PROPERTY_TYPES = {
    "affiliation": {
        "id": "CorporateBody",
        "name": "Corporate Body",
    },
    "professionOrOccupation": {
        "id": "SubjectHeading",
        "name": "Subject Heading",
    },
    "placeOfBirth": {
        "id": "PlaceOrGeographicName",
        "name": "Place or Geographic Name",
    },
    "placeOfDeath": {
        "id": "PlaceOrGeographicName",
        "name": "Place or Geographic Name",
    },
    "placeOfActivity": {
        "id": "PlaceOrGeographicName",
        "name": "Place or Geographic Name",
    },
    "familialRelationship": {
        "id": "Person",
        "name": "Person",
    },
    "relatedPerson": {
        "id": "Person",
        "name": "Person",
    },
    "relatedTerm": {
        "id": "SubjectHeading",
        "name": "Subject Heading",
    },
    "broaderTermGeneral": {
        "id": "SubjectHeading",
        "name": "Subject Heading",
    },
    "broaderTermInstantial": {
        "id": "SubjectHeading",
        "name": "Subject Heading",
    },
    "broaderTermPartitive": {
        "id": "SubjectHeading",
        "name": "Subject Heading",
    },
}

def service_manifest_response() -> dict:
    return {
        "versions": ["0.2"],
        "name": "Local GND Reconciliation Service",
        "identifierSpace": "https://d-nb.info/gnd/",
        "schemaSpace": "https://d-nb.info/gnd/",
        "defaultTypes": GND_TYPES,
        "batchSize": 50,
        "view": {
            "url": "https://d-nb.info/gnd/{{id}}"
        },
        "preview": {
            "url": f"{BASE_URL}/preview/{{{{id}}}}",
            "width": 430,
            "height": 300
        },
        "suggest": {
            "entity": {
                "service_url": BASE_URL,
                "service_path": "/suggest/entity"
            },
            "type": {
                "service_url": BASE_URL,
                "service_path": "/suggest/type"
            },
            "property": {
                "service_url": BASE_URL,
                "service_path": "/suggest/property"
            }
        },
        "extend": {
            "propose_properties": {
                "service_url": BASE_URL,
                "service_path": "/properties"
            },
            "property_settings": [
                {
                    "name": "limit",
                    "label": "Limit",
                    "type": "number",
                    "default": 0,
                    "help_text": "Maximum number of values to return per row. Use 0 for no limit."
                },
                {
                    "name": "content",
                    "label": "Content",
                    "type": "select",
                    "default": "literal",
                    "help_text": "Return either identifiers/URIs or readable literal labels.",
                    "choices": [
                        {
                            "value": "id",
                            "name": "ID"
                        },
                        {
                            "value": "literal",
                            "name": "Literal"
                        }
                    ]
                }
            ]
        }
    }

@app.get(
    "/",
    tags=["OpenRefine"],
    summary="Service manifest, reconciliation query, or extend query",
    description=(
        "Root endpoint according to the OpenRefine Reconciliation API. "
        "Without parameters it returns the service manifest. "
        "With `queries` it handles a reconciliation batch. "
        "With `query` it handles a simple entity query. "
        "With `extend` it handles a data extension request."
    ),
    operation_id="openrefine_root_get",
)
def root_get(
    queries: str | None = Query(
        default=None,
        description="JSON-encoded OpenRefine reconciliation query batch.",
        examples=[
            '{"q1":{"query":"Goethe","type":"DifferentiatedPerson"}}'
        ],
    ),
    query: str | None = Query(
        default=None,
        description="Simple query string for quick entity search.",
        examples=["Goethe"],
    ),
    extend: str | None = Query(
        default=None,
        description="JSON-encoded OpenRefine data extension request.",
        examples=[
            '{"ids":["118540238"],"properties":[{"id":"preferredName"},{"id":"dateOfBirth"}]}'
        ],
    ),
    limit: int = Query(
        default=5,
        ge=1,
        le=100,
        description="Maximum number of candidates to return.",
    ),
):
    """
    Root endpoint according to Reconciliation API v0.2.

    GET /              -> service manifest
    GET /?queries=...  -> reconciliation query batch
    GET /?query=...    -> simple entity query
    GET /?extend=...   -> data extension query
    """

    if queries:
        try:
            parsed_queries = json.loads(queries)
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
            limit=limit,
        )

    if query:
        return {
            "result": search_gnd(
                query=query,
                limit=limit,
            )
        }

    if extend:
        try:
            extend_request = json.loads(extend)
        except json.JSONDecodeError as error:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Invalid JSON in 'extend' parameter",
                    "details": str(error),
                },
            )

        return handle_extend_request(extend_request)

    return service_manifest_response()

@app.post(
    "/",
    tags=["OpenRefine"],
    summary="OpenRefine reconciliation or extend request",
    description=(
        "Handles OpenRefine-compatible form-encoded POST requests. "
        "Use the `queries` form field for reconciliation and the `extend` "
        "form field for data extension."
    ),
    operation_id="openrefine_root_post",
    openapi_extra=OPENREFINE_POST_OPENAPI_EXTRA,
)
async def root_post(request: Request):
    """
    Root POST endpoint according to Reconciliation API v0.2.

    Supports:
    - queries=... for reconciliation
    - extend=... for data extension
    """

    return await parse_and_handle_root_post(request)

@app.head(
    "/",
    include_in_schema=False,
)
def service_manifest_head():
    """
    Allows HEAD checks for the service manifest endpoint.
    Some clients or diagnostic tools may use HEAD before GET.
    """

    return Response(status_code=200)


@app.get("/health")
def health():
    """
    Simple health endpoint.
    """

    return {
        "status": "ok"
    }

@app.get("/preview", response_class=HTMLResponse,
         tags=['Preview'],
         summary='preview a GND entity',
         description='Returns an HTML preview for a given GND entity.')
def preview_by_query(id: str = Query(...)):
    html, status_code = render_preview_for_id(id)

    return HTMLResponse(
        content=html,
        status_code=status_code,
    )


@app.get("/preview/{gnd_id}", response_class=HTMLResponse,
         tags=['Preview'],
         summary='preview a GND entity by ID',
         description='Returns an HTML preview for a given GND entity by its GND ID.')
def preview_by_path(gnd_id: str):
    html, status_code = render_preview_for_id(gnd_id)

    return HTMLResponse(
        content=html,
        status_code=status_code,
    )

@app.get(
    "/suggest/entity",
    tags=["Suggest"],
    summary="Suggest GND entities",
    description="Returns entity suggestions for OpenRefine based on a prefix.",
)
def suggest_entity(
    prefix: str = Query(default=""),
    cursor: int = Query(default=0),
    limit: int = Query(default=10),
    type: str | None = Query(default=None),
):
    """
    Suggests GND entities for OpenRefine.

    Example:
    /suggest/entity?prefix=Goethe
    /suggest/entity?prefix=Goethe&cursor=0
    """

    if not prefix or not prefix.strip():
        return {
            "result": []
        }

    results = search_gnd(
        query=prefix,
        limit=cursor + limit,
        entity_type=type,
    )

    paged_results = results[cursor : cursor + limit]

    suggestions = []

    for result in paged_results:
        suggestions.append(
            {
                "id": result.get("id"),
                "name": result.get("name"),
                "type": result.get("type", []),
                "score": result.get("score"),
            }
        )

    return {
        "result": suggestions
    }

@app.get(
    "/suggest/type",
    tags=["Suggest"],
    summary="Suggest GND types",
    description="Returns available GND entity types.",
)
def suggest_type(
    prefix: str = Query(default=""),
    cursor: int = Query(default=0),
    limit: int = Query(default=10),
):
    """
    Suggests supported GND entity types for OpenRefine.

    Example:
    /suggest/type?prefix=Per
    /suggest/type?prefix=Per&cursor=0
    """

    normalized_prefix = prefix.strip().lower()

    if not normalized_prefix:
        matching_types = GND_TYPES
    else:
        matching_types = []

        for gnd_type in GND_TYPES:
            type_id = gnd_type["id"].lower()
            type_name = gnd_type["name"].lower()

            if (
                normalized_prefix in type_id
                or normalized_prefix in type_name
            ):
                matching_types.append(gnd_type)

    return {
        "result": matching_types[cursor : cursor + limit]
    }

@app.get(
    "/suggest/property",
    tags=["Suggest"],
    summary="Suggest extend properties",
    description="Returns available properties for Add columns from reconciled values.",
)
def suggest_property(
    prefix: str = Query(default=""),
    cursor: int = Query(default=0),
    limit: int = Query(default=10),
    type: str | None = Query(default=None),
):
    return {
        "result": suggest_registry_properties(
            prefix=prefix,
            entity_type=type,
            cursor=cursor,
            limit=limit,
        )
    }

@app.get("/properties")
def propose_properties(
    type: str = Query(default=""),
    limit: int = Query(default=200),
):
    return {
        "type": type,
        "limit": limit,
        "properties": get_registry_properties_for_type(
            entity_type=type or None,
            limit=limit,
        ),
    }

@app.get("/extend")
def extend_get(
    extend: str | None = Query(default=None),
):
    """
    Handles GET-based OpenRefine data extension requests.

    Example:
    /extend?extend={"ids":["118540238"],"properties":[{"id":"preferredName"}]}
    """

    if not extend:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Missing required parameter: 'extend'"
            },
        )

    try:
        extend_request = json.loads(extend)
    except json.JSONDecodeError as error:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Invalid JSON in 'extend' parameter",
                "details": str(error),
            },
        )

    return handle_extend_request(extend_request)

@app.post(
    "/extend",
    tags=["Extend"],
    summary="Extend reconciled GND entities",
    description="Returns additional property values for already reconciled GND IDs.",
    response_model=ExtendResponse,
)
async def extend_post(request: Request):
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        try:
            extend_request = await request.json()
        except json.JSONDecodeError as error:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Invalid JSON body",
                    "details": str(error),
                },
            )
        except UnicodeDecodeError as error:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Invalid request body encoding",
                    "details": str(error),
                },
            )

        if not isinstance(extend_request, dict):
            return JSONResponse(
                status_code=400,
                content={
                    "error": "JSON body must be an object",
                },
            )

        return handle_extend_request(extend_request)

    form = await request.form()
    extend = form.get("extend")

    if not extend:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Missing JSON body or form field: 'extend'",
            },
        )

    try:
        extend_request = json.loads(extend)
    except json.JSONDecodeError as error:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Invalid JSON in 'extend' form field",
                "details": str(error),
            },
        )

    return handle_extend_request(extend_request)

@app.post(
    "/extend/json",
    tags=["Extend"],
    summary="Extend reconciled GND entities with JSON body",
    response_model=ExtendResponse,
)
def extend_json(payload: ExtendRequest):
    return handle_extend_request(payload.model_dump())

@app.get(
    "/reconcile",
    tags=["OpenRefine"],
    summary="GET reconciliation query alias",
    description="GET alias for reconciliation query batches using the `queries` query parameter.",
    operation_id="openrefine_reconcile_get",
)
def reconcile_get(
    queries: str | None = Query(
        default=None,
        description="JSON-encoded OpenRefine reconciliation query batch.",
    ),
    query: str | None = Query(
        default=None,
        description="Simple query string for quick entity search.",
    ),
    limit: int = Query(default=5, ge=1, le=100),
):
    if queries:
        try:
            parsed_queries = json.loads(queries)
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
            limit=limit,
        )

    if query:
        return {
            "result": search_gnd(
                query=query,
                limit=limit,
            )
        }

    return JSONResponse(
        status_code=400,
        content={
            "error": "Missing required parameter: 'queries' or 'query'"
        },
    )


@app.post(
    "/reconcile",
    tags=["OpenRefine"],
    summary="Reconciliation query alias",
    description=(
        "Alias for OpenRefine-compatible reconciliation requests. "
        "Accepts the same form-encoded `queries` payload as `POST /`."
    ),
    operation_id="openrefine_reconcile_post",
    openapi_extra=OPENREFINE_POST_OPENAPI_EXTRA,
)
async def reconcile_post(request: Request):
    """
    POST /reconcile alias for OpenRefine reconciliation requests.
    """

    return await parse_and_handle_root_post(request)


@app.get(
    "/status/update",
    tags=["Status"],
    summary="Get OAI update status",
    description="Returns the state of the daily incremental OAI update process.",
    response_model=UpdateStatusResponse | dict,
)
def get_update_status():
    if not UPDATE_STATE_FILE.exists():
        return JSONResponse(
            {
                "enabled": True,
                "status": "not_run_yet",
                "message": "No OAI update has been executed yet.",
            }
        )

    try:
        state = json.loads(
            UPDATE_STATE_FILE.read_text(encoding="utf-8")
        )

    except FileNotFoundError:
        return JSONResponse(
            status_code=404,
            content={
                "status": "not_found",
                "message": "Update state file does not exist.",
            },
        )

    except json.JSONDecodeError as error:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Update state file contains invalid JSON.",
                "error": str(error),
            },
        )

    except OSError as error:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Could not read update state file.",
                "error": str(error),
            },
        )

    return state


def handle_reconciliation_queries(
    queries: dict,
    limit: int = 5,
) -> dict:
    """
    Processes OpenRefine-style batched reconciliation queries.
    """

    response = {}

    for query_id, query_object in queries.items():
        if isinstance(query_object, str):
            query_text = query_object
            entity_type = None
            details = []
            query_limit = limit

        elif isinstance(query_object, dict):
            query_text = query_object.get("query", "")
            entity_type = extract_entity_type(query_object)
            details = extract_reconciliation_properties(query_object)
            query_limit = query_object.get("limit", limit)

        else:
            response[query_id] = {
                "result": []
            }
            continue

        results = search_gnd(
            query=query_text,
            limit=query_limit,
            entity_type=entity_type,
            properties=details,
        )

        response[query_id] = {
            "result": results
        }

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


async def parse_and_handle_root_post(request: Request):
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
            )

        if "extend" in body_json:
            return handle_extend_request(body_json["extend"])

        # Fallback: treat JSON object as a reconciliation batch
        return handle_reconciliation_queries(
            queries=body_json,
            limit=5,
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

        return handle_extend_request(extend_request)

    return JSONResponse(
        status_code=400,
        content={
            "error": "Missing 'queries' or 'extend' parameter"
        },
    )

def should_resolve_gnd_uri(prop_id: str) -> bool:
    return prop_id in {
        "professionOrOccupation",
        "placeOfBirth",
        "placeOfDeath",
        "placeOfActivity",
    }



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
