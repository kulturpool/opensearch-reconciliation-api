import json
import logging
import sys
from pathlib import Path

# Add parent directory to path to allow imports from config
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.models.openapi_models import UpdateStatusResponse
from api.routers.reconciliation import build_reconciliation_router
from api.vocabularies.getty import GETTY_VOCAB
from api.vocabularies.gnd import GND_VOCAB
from config import DATA_DIR

# uvicorn only configures its own "uvicorn.*" loggers by default, so make sure
# application loggers (e.g. reconciliation batch timing logs) actually get
# emitted instead of being silently dropped by the root logger.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

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

app.include_router(build_reconciliation_router(GND_VOCAB))
app.include_router(build_reconciliation_router(GETTY_VOCAB), prefix="/getty")


@app.get("/health")
def health():
    """
    Simple health endpoint.
    """

    return {"status": "ok"}


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
