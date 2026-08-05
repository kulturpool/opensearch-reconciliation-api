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

from api.services.vocab_resolver import resolve_gnd_vocab_uri

from fastapi.responses import HTMLResponse
from api.services.preview import render_preview_for_id

app = FastAPI(
    title="Local GND Reconciliation API",
    version="0.1.0",
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

@app.get("/")
def root_get(
    queries: str | None = Query(default=None),
    query: str | None = Query(default=None),
    extend: str | None = Query(default=None),
    limit: int = Query(default=5),
):
    """
    Root endpoint according to Reconciliation API v0.2.

    GET /              -> service manifest
    GET /?queries=...  -> reconciliation query batch
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

@app.post("/")
async def root_post(request: Request):
    """
    Root POST endpoint according to Reconciliation API v0.2.

    Supports:
    - queries=... for reconciliation
    - extend=... for data extension
    """

    return await parse_and_handle_root_post(request)

@app.head("/")
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

@app.get("/preview", response_class=HTMLResponse)
def preview_by_query(id: str = Query(...)):
    html, status_code = render_preview_for_id(id)

    return HTMLResponse(
        content=html,
        status_code=status_code,
    )


@app.get("/preview/{gnd_id}", response_class=HTMLResponse)
def preview_by_path(gnd_id: str):
    html, status_code = render_preview_for_id(gnd_id)

    return HTMLResponse(
        content=html,
        status_code=status_code,
    )

@app.get("/suggest/entity")
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

@app.get("/suggest/type")
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

@app.get("/suggest/property")
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

@app.get("/reconcile")
def reconcile_get(
    queries: str | None = Query(default=None),
    query: str | None = Query(default=None),
    limit: int = Query(default=5),
):
    """
    Handles GET-based reconciliation requests.

    Supports:
    1. OpenRefine-style batched requests via ?queries={...}
    2. Simple test requests via ?query=Goethe
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
        results = search_gnd(
            query=query,
            limit=limit,
        )

        return {
            "result": results
        }

    return JSONResponse(
        status_code=400,
        content={
            "error": "Missing required parameter: 'queries' or 'query'"
        },
    )


@app.post("/reconcile")
async def reconcile_post(request: Request):
    return await parse_and_handle_root_post(request)


@app.post("/extend")
async def extend_post(request: Request):
    return await parse_and_handle_root_post(request)


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


def handle_extend_request(extend_request: dict) -> dict:
    """
    Processes an OpenRefine extend request.

    Expected input:
    {
      "ids": ["118540238"],
      "properties": [
        {"id": "preferredName"},
        {"id": "dateOfBirth"}
      ]
    }

    Expected output:
    {
      "meta": [...],
      "rows": {
        "118540238": {
          "preferredName": [{"str": "..."}]
        }
      }
    }
    """

    ids = extend_request.get("ids", [])
    properties = extend_request.get("properties", [])

    if not isinstance(ids, list):
        ids = []

    if not isinstance(properties, list):
        properties = []

    meta = build_extend_meta(properties)

    rows = {}

    for gnd_id in ids:
        record = get_gnd_record_by_id(str(gnd_id))

        if record is None:
            rows[str(gnd_id)] = {}
            continue

        rows[str(gnd_id)] = build_extend_row(
            record=record,
            properties=properties,
        )

    return {
        "meta": meta,
        "rows": rows,
    }


def build_extend_meta(properties: list[dict]) -> list:
    """
    Builds metadata for requested properties.

    If a property usually returns GND entities, we announce a type.
    This helps OpenRefine treat returned values as reconciled entities.
    """

    meta = []

    for prop in properties:
        prop_id = prop.get("id")

        if not prop_id:
            continue

        meta_item = {
            "id": prop_id,
            "name": property_label(prop_id),
        }

        relation_type = RELATION_PROPERTY_TYPES.get(prop_id)

        if relation_type:
            meta_item["type"] = relation_type

        meta.append(meta_item)

    return meta


def build_extend_row(
    record: dict,
    properties: list[dict],
) -> dict:
    """
    Builds one row of property values for one GND record.
    """

    row = {}

    for prop in properties:
        prop_id = prop.get("id")

        if not prop_id:
            continue

        settings = get_extend_property_settings(prop)

        value = get_property_values_from_record(record, prop_id)

        values = format_extend_values(
            prop_id=prop_id,
            value=value,
            content=settings["content"],
        )

        values = apply_extend_limit(
            values=values,
            limit=settings["limit"],
        )

        row[prop_id] = values

    return row

def apply_extend_limit(
    values: list,
    limit: int,
) -> list:
    """
    Applies OpenRefine limit setting.

    limit = 0 means no limit.
    """

    if limit <= 0:
        return values

    return values[:limit]


def format_extend_values(
    prop_id: str,
    value,
    content: str = "literal",
) -> list:
    """
    Converts a value into OpenRefine extend cell format.

    content="id":
      Return raw identifiers / URIs.

    content="literal":
      Return readable labels / literals.
    """

    if value is None:
        return []

    if isinstance(value, list):
        result = []

        for item in value:
            result.extend(
                format_extend_values(
                    prop_id=prop_id,
                    value=item,
                    content=content,
                )
            )

        return result

    if isinstance(value, dict):
        return format_extend_dict_value(
            value=value,
            content=content,
        )

    value_string = str(value)

    if content == "id":
        return [
            {
                "str": format_identifier_value(value_string)
            }
        ]

    # literal mode
    resolved_value = resolve_extend_value(value_string)

    if resolved_value:
        return [
            {
                "str": resolved_value
            }
        ]

    return [
        {
            "str": value_string
        }
    ]

def format_extend_dict_value(
    value: dict,
    content: str = "literal",
) -> list:
    """
    Formats dict values for OpenRefine extend output.
    """

    if content == "id":
        identifier = (
            value.get("id")
            or value.get("@id")
            or value.get("uri")
            or value.get("value")
            or value.get("str")
            or value.get("name")
        )

        if identifier is None:
            return []

        return [
            {
                "str": format_identifier_value(str(identifier))
            }
        ]

    label = (
        value.get("label")
        or value.get("name")
        or value.get("str")
        or value.get("value")
        or value.get("id")
        or value.get("@id")
    )

    if label is None:
        return []

    label_string = str(label)

    resolved_value = resolve_extend_value(label_string)

    if resolved_value:
        label_string = resolved_value

    return [
        {
            "str": label_string
        }
    ]


def format_identifier_value(value: str) -> str:
    """
    Formats identifier values for content='id'.

    Currently returns raw URI/identifier. This mirrors the ID/link mode.
    """

    return value

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


def resolve_gnd_uri_to_label(value: str) -> str | None:
    """
    Resolves a GND URI to the preferredName of the referenced local record.

    Example:
    https://d-nb.info/gnd/1008453-8
    -> Universität Leipzig
    """

    if not value.startswith(GND_URI_PREFIX):
        return None

    gnd_id = value.replace(GND_URI_PREFIX, "").strip("/")

    if not gnd_id:
        return None

    record = get_gnd_record_by_id(gnd_id)

    if not record:
        return None

    preferred_name = record.get("preferredName")

    if not preferred_name:
        return None

    return preferred_name

def resolve_extend_value(value: str) -> str | None:
    """
    Resolves values returned by /extend.

    Handles:
    - normal GND entity URIs, e.g. https://d-nb.info/gnd/1008453-8
    - GND vocabulary URIs, e.g.
      https://d-nb.info/standards/vocab/gnd/geographic-area-code#XA-DE
    """

    resolved_gnd_entity = resolve_gnd_uri_to_label(value)

    if resolved_gnd_entity:
        return resolved_gnd_entity

    resolved_vocab_value = resolve_gnd_vocab_uri(value)

    if resolved_vocab_value:
        return resolved_vocab_value

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

def get_extend_property_settings(prop: dict) -> dict:
    """
    Extracts OpenRefine data extension settings for a requested property.

    Example:
    {
      "id": "geographicAreaCode",
      "settings": {
        "limit": "1",
        "content": "id"
      }
    }
    """

    settings = prop.get("settings", {})

    if not isinstance(settings, dict):
        settings = {}

    content = settings.get("content", "literal")

    if content not in {"id", "literal"}:
        content = "literal"

    limit = parse_extend_limit(settings.get("limit", 0))

    return {
        "content": content,
        "limit": limit,
    }


def parse_extend_limit(value) -> int:
    """
    Parses OpenRefine limit setting.

    0 means no limit.
    """

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0

    if parsed < 0:
        return 0

    return parsed