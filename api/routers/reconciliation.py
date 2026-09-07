"""
Route factory for the OpenRefine-compatible reconciliation API.

`build_reconciliation_router(vocab)` builds an `APIRouter` containing all
reconciliation, suggest, extend and preview routes for a single vocabulary
(e.g. GND or, later, Getty). The same router shape can be mounted multiple
times at different prefixes for different vocabularies.

`/health` and `/status/update` are intentionally NOT part of this router -
they are operational, vocabulary-agnostic endpoints that stay directly on
the FastAPI app (see api/main.py).
"""

import json
from typing import Any

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from api.models.openapi_models import ExtendRequest, ExtendResponse
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
from api.vocabularies.base import VocabConfig

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


def build_reconciliation_router(
    vocab: VocabConfig,
    operation_id_prefix: str | None = None,
) -> APIRouter:
    """
    Builds an APIRouter with all reconciliation, suggest, extend and preview
    routes wired to the given `vocab`.

    `operation_id_prefix` lets the same `vocab` be mounted at more than one
    URL prefix (e.g. GND at both `/` and `/gnd`) without producing duplicate
    OpenAPI `operationId`s; it defaults to `vocab.key`.
    """

    op_id = operation_id_prefix or vocab.key
    router = APIRouter()

    @router.get(
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
        operation_id=f"openrefine_root_get_{op_id}",
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
                vocab=vocab,
            )

        if query:
            return {
                "result": search_gnd(
                    query=query,
                    limit=limit,
                    vocab=vocab,
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

            return handle_extend_request(extend_request, vocab=vocab)

        return service_manifest_response(vocab=vocab)

    @router.post(
        "/",
        tags=["OpenRefine"],
        summary="OpenRefine reconciliation or extend request",
        description=(
            "Handles OpenRefine-compatible form-encoded POST requests. "
            "Use the `queries` form field for reconciliation and the `extend` "
            "form field for data extension."
        ),
        operation_id=f"openrefine_root_post_{op_id}",
        openapi_extra=OPENREFINE_POST_OPENAPI_EXTRA,
    )
    async def root_post(request: Request):
        """
        Root POST endpoint according to Reconciliation API v0.2.

        Supports:
        - queries=... for reconciliation
        - extend=... for data extension
        """

        return await parse_and_handle_root_post(request, vocab=vocab)

    @router.head(
        "/",
        include_in_schema=False,
    )
    def service_manifest_head():
        """
        Allows HEAD checks for the service manifest endpoint.
        Some clients or diagnostic tools may use HEAD before GET.
        """

        return Response(status_code=200)

    @router.get(
        "/preview",
        response_class=HTMLResponse,
        tags=["Preview"],
        summary="preview an entity",
        description="Returns an HTML preview for a given entity.",
        operation_id=f"preview_by_query_{op_id}",
    )
    def preview_by_query(id: str = Query(...)):
        html, status_code = render_preview_for_id(id, vocab=vocab)

        return HTMLResponse(
            content=html,
            status_code=status_code,
        )

    @router.get(
        "/preview/{entity_id:path}",
        response_class=HTMLResponse,
        tags=["Preview"],
        summary="preview an entity by ID",
        description="Returns an HTML preview for a given entity by its ID.",
        operation_id=f"preview_by_path_{op_id}",
    )
    def preview_by_path(entity_id: str):
        html, status_code = render_preview_for_id(entity_id, vocab=vocab)

        return HTMLResponse(
            content=html,
            status_code=status_code,
        )

    @router.get(
        "/suggest/entity",
        tags=["Suggest"],
        summary="Suggest entities",
        description="Returns entity suggestions for OpenRefine based on a prefix.",
        operation_id=f"suggest_entity_{op_id}",
    )
    def suggest_entity(
        prefix: str = Query(default=""),
        cursor: int = Query(default=0),
        limit: int = Query(default=10),
        type: str | None = Query(default=None),
    ):
        """
        Suggests entities for OpenRefine.

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
            vocab=vocab,
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

    @router.get(
        "/suggest/type",
        tags=["Suggest"],
        summary="Suggest types",
        description="Returns available entity types.",
        operation_id=f"suggest_type_{op_id}",
    )
    def suggest_type(
        prefix: str = Query(default=""),
        cursor: int = Query(default=0),
        limit: int = Query(default=10),
    ):
        """
        Suggests supported entity types for OpenRefine.

        Example:
        /suggest/type?prefix=Per
        /suggest/type?prefix=Per&cursor=0
        """

        normalized_prefix = prefix.strip().lower()

        if not normalized_prefix:
            matching_types = list(vocab.types)
        else:
            matching_types = []

            for entity_type in vocab.types:
                type_id = entity_type["id"].lower()
                type_name = entity_type["name"].lower()

                if normalized_prefix in type_id or normalized_prefix in type_name:
                    matching_types.append(entity_type)

        return {"result": matching_types[cursor : cursor + limit]}

    @router.get(
        "/suggest/property",
        tags=["Suggest"],
        summary="Suggest extend properties",
        description="Returns available properties for Add columns from reconciled values.",
        operation_id=f"suggest_property_{op_id}",
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
                vocab=vocab,
            )
        }

    @router.get(
        "/properties",
        operation_id=f"propose_properties_{op_id}",
    )
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
                vocab=vocab,
            ),
        }

    @router.get(
        "/extend",
        operation_id=f"extend_get_{op_id}",
    )
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

        return handle_extend_request(extend_request, vocab=vocab)

    @router.post(
        "/extend",
        tags=["Extend"],
        summary="Extend reconciled entities",
        description="Returns additional property values for already reconciled entity IDs.",
        response_model=ExtendResponse,
        operation_id=f"extend_post_{op_id}",
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

            return handle_extend_request(extend_request, vocab=vocab)

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

        return handle_extend_request(extend_request, vocab=vocab)

    @router.post(
        "/extend/json",
        tags=["Extend"],
        summary="Extend reconciled entities with JSON body",
        response_model=ExtendResponse,
        operation_id=f"extend_json_{op_id}",
    )
    def extend_json(payload: ExtendRequest):
        return handle_extend_request(payload.model_dump(), vocab=vocab)

    @router.get(
        "/reconcile",
        tags=["OpenRefine"],
        summary="GET reconciliation query alias",
        description="GET alias for reconciliation query batches using the `queries` query parameter.",
        operation_id=f"openrefine_reconcile_get_{op_id}",
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
                vocab=vocab,
            )

        if query:
            return {
                "result": search_gnd(
                    query=query,
                    limit=limit,
                    vocab=vocab,
                )
            }

        return JSONResponse(
            status_code=400,
            content={"error": "Missing required parameter: 'queries' or 'query'"},
        )

    @router.post(
        "/reconcile",
        tags=["OpenRefine"],
        summary="Reconciliation query alias",
        description=(
            "Alias for OpenRefine-compatible reconciliation requests. "
            "Accepts the same form-encoded `queries` payload as `POST /`."
        ),
        operation_id=f"openrefine_reconcile_post_{op_id}",
        openapi_extra=OPENREFINE_POST_OPENAPI_EXTRA,
    )
    async def reconcile_post(request: Request):
        """
        POST /reconcile alias for OpenRefine reconciliation requests.
        """

        return await parse_and_handle_root_post(request, vocab=vocab)

    return router
