import json
from urllib.parse import parse_qs

from fastapi import FastAPI, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from api.services.search import get_gnd_record_by_id, search_gnd
from fastapi.middleware.cors import CORSMiddleware

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

GND_TYPES = [ # Definition of the GND types, adapted to the existing reconcilition services - check if they fit the data
    {
        "id": "DifferentiatedPerson",
        "name": "Individualisierte Person"
    },
    {
        "id": "CorporateBody",
        "name": "Körperschaft"
    },
    {
        "id": "ConferenceOrEvent",
        "name": "Konferenz oder Veranstaltung"
    },
    {
        "id": "PlaceOrGeographicName",
        "name": "Geografikum"
    },
    {
        "id": "SubjectHeading",
        "name": "Schlagwort"
    },
    {
        "id": "Work",
        "name": "Werk"
    },
    {
        "id": "Family",
        "name": "Familie"
    },
    {
        "id": "AuthorityResource",
        "name": "Normdatenressource"
    },
    {
        "id": "TerritorialCorporateBodyOrAdministrativeUnit",
        "name": "Territorial Corporate Body or Administrative Unit",
        "broader": [
            {
                "id": "PlaceOrGeographicName",
                "name": "Place or Geographic Name"
            }
        ]
    }
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
            }
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

@app.get("/preview/{gnd_id}", response_class=HTMLResponse)
def preview(gnd_id: str):
    """
    Returns a small HTML preview for OpenRefine candidate flyouts.
    """

    record = get_gnd_record_by_id(gnd_id)

    if record is None:
        return HTMLResponse(
            content=f"""
            <html>
              <body style="font-family: sans-serif; padding: 12px;">
                <h3>GND record not found</h3>
                <p>No record found for GND ID: <code>{escape_html(gnd_id)}</code></p>
              </body>
            </html>
            """,
            status_code=404,
        )

    return HTMLResponse(
        content=render_gnd_preview(record),
        status_code=200,
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

    Expected input:
    {
      "q1": {
        "query": "Goethe",
        "type": "Person"
      }
    }

    Expected output:
    {
      "q1": {
        "result": [...]
      }
    }
    """

    response = {}

    for query_id, query_object in queries.items():
        if isinstance(query_object, str):
            query_text = query_object
            entity_type = None
        else:
            query_text = query_object.get("query", "")
            entity_type = extract_entity_type(query_object)

        results = search_gnd(
            query=query_text,
            limit=limit,
            entity_type=entity_type,
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

def render_gnd_preview(record: dict) -> str:
    """
    Renders a GND record as a small HTML preview.
    """

    gnd_id = escape_html(record.get("id", ""))
    preferred_name = escape_html(record.get("preferredName", ""))
    uri = escape_html(record.get("uri", f"https://d-nb.info/gnd/{gnd_id}"))

    entity_types = record.get("type", [])
    variant_names = record.get("variantName", [])

    date_of_birth = record.get("dateOfBirth")
    date_of_death = record.get("dateOfDeath")

    profession = record.get("professionOrOccupation", [])
    place_of_birth = record.get("placeOfBirth")
    place_of_death = record.get("placeOfDeath")

    html = f"""
    <html>
      <head>
        <meta charset="utf-8" />
      </head>
      <body style="font-family: Arial, sans-serif; font-size: 13px; padding: 12px; line-height: 1.4;">
        <h3 style="margin-top: 0; margin-bottom: 6px;">
          {preferred_name}
        </h3>

        <div style="color: #555; margin-bottom: 8px;">
          GND-ID: <strong>{gnd_id}</strong>
        </div>

        {render_list_block("Typ", entity_types)}

        {render_life_dates(date_of_birth, date_of_death)}

        {render_list_block("Variantenamen", variant_names)}

        {render_list_block("Beruf / Tätigkeit", profession)}

        {render_value_block("Geburtsort", place_of_birth)}

        {render_value_block("Sterbeort", place_of_death)}

        <div style="margin-top: 12px;">
          {uri}
            Datensatz bei d-nb.info öffnen
          </a>
        </div>
      </body>
    </html>
    """

    return html

def render_life_dates(
    date_of_birth: str | None,
    date_of_death: str | None,
) -> str:
    """
    Renders birth/death dates if available.
    """

    if not date_of_birth and not date_of_death:
        return ""

    birth = escape_html(date_of_birth or "")
    death = escape_html(date_of_death or "")

    if birth and death:
        value = f"{birth} – {death}"
    elif birth:
        value = f"* {birth}"
    else:
        value = f"† {death}"

    return f"""
    <div style="margin-bottom: 8px;">
      <strong>Lebensdaten:</strong><br />
      {value}
    </div>
    """

def render_list_block(label: str, values) -> str:
    """
    Renders a list-like field.
    """

    if not values:
        return ""

    if isinstance(values, str):
        values = [values]

    if not isinstance(values, list):
        values = [str(values)]

    items = "".join(
        f"<li>{escape_html(str(value))}</li>"
        for value in values
        if value
    )

    if not items:
        return ""

    return f"""
    <div style="margin-bottom: 8px;">
      <strong>{escape_html(label)}:</strong>
      <ul style="margin-top: 4px; padding-left: 18px;">
        {items}
      </ul>
    </div>
    """

def render_value_block(label: str, value) -> str:
    """
    Renders one simple value.
    """

    if not value:
        return ""

    if isinstance(value, list):
        value = ", ".join(str(item) for item in value if item)

    return f"""
    <div style="margin-bottom: 8px;">
      <strong>{escape_html(label)}:</strong><br />
      {escape_html(str(value))}
    </div>
    """

def escape_html(value: str) -> str:
    """
    Minimal HTML escaping to avoid broken preview markup.
    """

    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )

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

        value = get_property_values_from_record(record, prop_id)

        row[prop_id] = format_extend_values(prop_id, value)

    return row


def format_extend_values(prop_id: str, value) -> list:
    """
    Converts a value into OpenRefine extend cell format.

    - GND entity URIs become reconciled entity values:
      {"id": "...", "name": "...", "type": [...]}

    - GND vocabulary URIs such as geographic-area-code become strings.

    - Plain literals remain strings.
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
                )
            )

        return result

    if isinstance(value, dict):
        if "id" in value and "name" in value:
            return [value]

        label = (
            value.get("label")
            or value.get("name")
            or value.get("id")
            or str(value)
        )

        return [
            {
                "str": str(label)
            }
        ]

    value_string = str(value)

    reconciled_value = gnd_uri_to_reconciled_value(value_string)

    if reconciled_value:
        return [reconciled_value]

    resolved_vocab_value = resolve_gnd_vocab_uri(value_string)

    if resolved_vocab_value:
        return [
            {
                "str": resolved_vocab_value
            }
        ]

    return [
        {
            "str": value_string
        }
    ]

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