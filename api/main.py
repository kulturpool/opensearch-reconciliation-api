import dataclasses
import json
import logging
import sys
from pathlib import Path

# Add parent directory to path to allow imports from config
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.models.openapi_models import CombinedUpdateStatusResponse
from api.routers.reconciliation import build_reconciliation_router
from api.vocabularies.getty import (
    GETTY_VOCAB,
)
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
GETTY_STATE_FILE = DATA_DIR / "state" / "getty_state.json"

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
Local GND and Getty Reconciliation API which is compatible with OpenRefine.

This service provides:
- OpenRefine-compatible reconciliation
- entity, type and property suggest endpoints
- data extension / Add columns from reconciled values
- preview endpoint
- local GND and Getty index backed by OpenSearch
- regular updates
"""

app = FastAPI(
    title="OpenSearch Reconciliation API",
    summary="OpenRefine-compatible reconciliation service for GND and Getty Vocabularies.",
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
        "name": "See repository license and DNB and Getty data terms",
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
# Distinct /gnd URL mirroring /getty for usability. Uses a copy of GND_VOCAB
# with route_prefix="/gnd" so the service manifest advertises correct
# sub-endpoint URLs (e.g. /gnd/suggest/entity) for this mount; root "/"
# stays mounted as-is for backward compatibility with existing OpenRefine
# service configurations.
GND_VOCAB_PREFIXED = dataclasses.replace(GND_VOCAB, route_prefix="/gnd")
app.include_router(
    build_reconciliation_router(GND_VOCAB_PREFIXED, operation_id_prefix="gnd_prefixed"),
    prefix="/gnd",
)
# Getty runs as one combined service endpoint; the type dropdown lets
# clients pick AAT/ULAN/TGN/all instead of separate URLs per vocabulary.
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
    summary="Get GND and Getty update status",
    description=(
        "Returns the state of the regular incremental GND OAI update "
        "process and the Getty index build status."
    ),
    response_model=CombinedUpdateStatusResponse,
)
def get_update_status():
    gnd_status = (
        {
            "enabled": True,
            "status": "not_run_yet",
            "message": "No OAI update has been executed yet.",
        }
        if not UPDATE_STATE_FILE.exists()
        else read_state_file(
            UPDATE_STATE_FILE,
            "No OAI update has been executed yet.",
        )
    )

    getty_status = (
        {
            "initialized": False,
            "status": "not_built",
            "message": "No Getty build has been executed yet.",
        }
        if not GETTY_STATE_FILE.exists()
        else read_state_file(
            GETTY_STATE_FILE,
            "No Getty build has been executed yet.",
        )
    )

    return {
        "gnd": gnd_status,
        "getty": getty_status,
    }

def read_state_file(
    state_file: Path,
    not_found_message: str,
) -> dict:
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))

    except FileNotFoundError:
        return {
            "status": "not_found",
            "message": not_found_message,
        }

    except json.JSONDecodeError as error:
        return {
            "status": "error",
            "message": f"{state_file.name} contains invalid JSON.",
            "error": str(error),
        }

    except OSError as error:
        return {
            "status": "error",
            "message": f"Could not read {state_file.name}.",
            "error": str(error),
        }