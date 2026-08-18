"""
Centralized configuration module for environment variables.

All environment variables should be read here to avoid duplication
and provide a single source of truth for configuration.
"""

import os
from pathlib import Path

# =============================================================================
# OpenSearch Configuration
# =============================================================================

OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST", "opensearch")
OPENSEARCH_PORT = int(os.getenv("OPENSEARCH_PORT", "9200"))


# =============================================================================
# GND Index Configuration
# =============================================================================

INDEX_NAME = os.getenv("GND_INDEX_NAME", "gnd")
GND_FORCE_REINDEX = os.getenv("GND_FORCE_REINDEX", "false").lower() == "true"
GND_INDEX_ENTITYFACTS = os.getenv("GND_INDEX_ENTITYFACTS", "true").lower() == "true"
GND_ENTITYFACTS_ONLY_TYPE = os.getenv("GND_ENTITYFACTS_ONLY_TYPE") or None


# =============================================================================
# Index Build State Configuration
# =============================================================================

GND_INDEX_LOCK_STALE_SECONDS = int(
    os.getenv("GND_INDEX_LOCK_STALE_SECONDS", str(12 * 60 * 60))
)


# =============================================================================
# API Configuration
# =============================================================================

API_PORT = int(os.getenv("API_PORT", "8083"))
HOST_API_PORT = int(os.getenv("HOST_API_PORT", "8083"))
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8083")


# =============================================================================
# Data Paths
# =============================================================================

DATA_DIR = Path(os.getenv("GND_DATA_DIR", "data"))


# =============================================================================
# Update Scheduler Configuration
# =============================================================================

GND_AUTO_UPDATE = os.getenv("GND_AUTO_UPDATE", "true").lower() == "true"
GND_UPDATE_INTERVAL_HOURS = float(os.getenv("GND_UPDATE_INTERVAL_HOURS", "24"))
GND_UPDATE_INITIAL_DELAY_SECONDS = int(
    os.getenv("GND_UPDATE_INITIAL_DELAY_SECONDS", "300")
)
GND_UPDATE_MODE = os.getenv("GND_UPDATE_MODE", "oai")
GND_UPDATE_LOCK_ENABLED = os.getenv("GND_UPDATE_LOCK_ENABLED", "true").lower() == "true"
GND_UPDATE_LOCK_STALE_SECONDS = int(
    os.getenv("GND_UPDATE_LOCK_STALE_SECONDS", str(6 * 60 * 60))
)


# =============================================================================
# OAI-PMH Harvesting Configuration
# =============================================================================

GND_OAI_BASE_URL = os.getenv(
    "GND_OAI_BASE_URL", "https://services.dnb.de/oai/repository"
)
GND_OAI_SET = os.getenv("GND_OAI_SET") or None
GND_OAI_METADATA_PREFIX = os.getenv("GND_OAI_METADATA_PREFIX", "RDFxml")
GND_OAI_OVERLAP_MINUTES = int(os.getenv("GND_OAI_OVERLAP_MINUTES", "60"))

# OAI Request timeouts and retries
GND_OAI_REQUEST_TIMEOUT_SECONDS = int(
    os.getenv("GND_OAI_REQUEST_TIMEOUT_SECONDS", "300")
)
GND_OAI_REQUEST_MAX_RETRIES = int(os.getenv("GND_OAI_REQUEST_MAX_RETRIES", "6"))
GND_OAI_REQUEST_BACKOFF_SECONDS = int(
    os.getenv("GND_OAI_REQUEST_BACKOFF_SECONDS", "10")
)
GND_OAI_PAGE_DELAY_SECONDS = float(os.getenv("GND_OAI_PAGE_DELAY_SECONDS", "2"))


# =============================================================================
# GND Record Upsert Configuration
# =============================================================================

GND_RECORD_JSONLD_URL_TEMPLATE = os.getenv(
    "GND_RECORD_JSONLD_URL_TEMPLATE", "https://d-nb.info/gnd/{id}/about/lds.jsonld"
)

GND_UPSERT_REQUEST_DELAY_SECONDS = float(
    os.getenv("GND_UPSERT_REQUEST_DELAY_SECONDS", "0.25")
)
GND_UPSERT_REQUEST_MAX_RETRIES = int(os.getenv("GND_UPSERT_REQUEST_MAX_RETRIES", "5"))
GND_UPSERT_REQUEST_BACKOFF_SECONDS = int(
    os.getenv("GND_UPSERT_REQUEST_BACKOFF_SECONDS", "2")
)
GND_UPSERT_FAILED_IDS_FILE = os.getenv(
    "GND_UPSERT_FAILED_IDS_FILE", "data/state/oai_failed_ids.jsonl"
)


# =============================================================================
# Helper Functions
# =============================================================================


def get_opensearch_client():
    """
    Returns OpenSearch client configuration as a dictionary.

    Returns:
        dict: Configuration dict with host and port
    """
    return {
        "host": OPENSEARCH_HOST,
        "port": OPENSEARCH_PORT,
    }
