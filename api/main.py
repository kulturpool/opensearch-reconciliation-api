import json
import sys
from pathlib import Path
from typing import Any

# Add parent directory to path to allow imports from config
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from api.constants import GND_TYPES
from api.models.openapi_models import (
    ExtendRequest,
    ExtendResponse,
    UpdateStatusResponse,
)
from api.reconciliation_utils import (
    handle_reconciliation_queries,
    parse_and_handle_root_post,
    service_manifest_response,
)
from api.services.preview import render_preview_for_id
from api.services.properties import handle_extend_request
from api.services.property_registry import (
    get_registry_properties_for_type,
    suggest_registry_properties,
)
from api.services.search import search_gnd
from config import DATA_DIR

UPDATE_STATE_FILE = DATA_DIR / "state" / "update_state.json"

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
        examples=['{"q1":{"query":"Goethe","type":"DifferentiatedPerson"}}'],
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

    return {"status": "ok"}


@app.get(
    "/preview",
    response_class=HTMLResponse,
    tags=["Preview"],
    summary="preview a GND entity",
    description="Returns an HTML preview for a given GND entity.",
)
def preview_by_query(id: str = Query(...)):
    html, status_code = render_preview_for_id(id)

    return HTMLResponse(
        content=html,
        status_code=status_code,
    )


@app.get(
    "/preview/{gnd_id}",
    response_class=HTMLResponse,
    tags=["Preview"],
    summary="preview a GND entity by ID",
    description="Returns an HTML preview for a given GND entity by its GND ID.",
)
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
        return {"result": []}

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

    return {"result": suggestions}


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

            if normalized_prefix in type_id or normalized_prefix in type_name:
                matching_types.append(gnd_type)

    return {"result": matching_types[cursor : cursor + limit]}


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
            content={"error": "Missing required parameter: 'extend'"},
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
        content={"error": "Missing required parameter: 'queries' or 'query'"},
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
        state = json.loads(UPDATE_STATE_FILE.read_text(encoding="utf-8"))

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
