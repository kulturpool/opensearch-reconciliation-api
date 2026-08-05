import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from opensearchpy import OpenSearch

import os

INDEX_NAME = os.getenv("GND_INDEX_NAME", "gnd")
GND_FORCE_REINDEX = os.getenv("GND_FORCE_REINDEX", "false").lower() == "true"

GND_INDEX_ENTITYFACTS = os.getenv("GND_INDEX_ENTITYFACTS", "true").lower() == "true"
GND_ENTITYFACTS_ONLY_TYPE = os.getenv("GND_ENTITYFACTS_ONLY_TYPE") or None

OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST", "opensearch")
OPENSEARCH_PORT = int(os.getenv("OPENSEARCH_PORT", "9200"))


DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
STATE_DIR = DATA_DIR / "state"
LOG_DIR = DATA_DIR / "logs"

STATE_FILE = STATE_DIR / "gnd_state.json"
BOOTSTRAP_LOG = LOG_DIR / "bootstrap_gnd.log"

INDEX_NAME = "gnd"

REQUIRED_SOURCES = [
    "sachbegriff",
    "geografikum",
    "werk",
    "koerperschaft",
    "kongress",
    "person",
]


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_directories() -> None:
    """
    Creates runtime directories.

    data/ is ignored by git and therefore must be created on first run.
    """

    DATA_DIR.mkdir(exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def log(message: str) -> None:
    ensure_directories()

    line = f"[{timestamp()}] {message}"
    print(line)

    with BOOTSTRAP_LOG.open("a", encoding="utf-8") as file:
        file.write(line + "\n")


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {}

    with STATE_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_state(state: dict[str, Any]) -> None:
    ensure_directories()

    STATE_FILE.write_text(
        json.dumps(
            state,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def get_opensearch_client() -> OpenSearch:
    return OpenSearch(
        hosts=[{"host": OPENSEARCH_HOST, "port": OPENSEARCH_PORT}],
        http_compress=True,
        use_ssl=False,
        verify_certs=False,
        ssl_show_warn=False,
    )


def wait_for_opensearch(timeout_seconds: int = 120) -> None:
    log("Waiting for OpenSearch...")

    client = get_opensearch_client()

    start = time.time()

    while True:
        try:
            info = client.info()
            version = info.get("version", {}).get("number")
            log(f"OpenSearch is available. Version: {version}")
            return
        except Exception as error:
            if time.time() - start > timeout_seconds:
                raise RuntimeError("OpenSearch did not become available in time") from error

            time.sleep(3)


def index_exists(index_name: str = INDEX_NAME) -> bool:
    client = get_opensearch_client()

    try:
        return client.indices.exists(index=index_name)
    except Exception:
        return False


def get_index_count(index_name: str = INDEX_NAME) -> int:
    client = get_opensearch_client()

    if not client.indices.exists(index=index_name):
        return 0

    response = client.count(index=index_name)
    return int(response.get("count", 0))


def run_command(command: list[str]) -> None:
    log("RUN " + " ".join(command))
    subprocess.run(command, check=True)


def download_missing_gnd_files() -> None:
    """
    Runs the downloader.

    The downloader itself skips existing files unless --force is used.
    """

    log("Downloading missing GND LDS source files")

    run_command(
        [
            sys.executable,
            "-m",
            "importer.download_gnd_lds",
            "--source",
            "all",
        ]
    )


def fetch_property_registry_if_needed(force: bool = False) -> None:
    """
    Fetches the property registry from the original GND reconciliation API
    if it is missing.
    """

    registry_file = Path("config/gnd_properties.json")

    if registry_file.exists() and not force:
        log("Property registry already exists. Skipping.")
        return

    script = Path("scripts/fetch_gnd_property_registry.py")

    if not script.exists():
        log("Property registry fetch script not found. Skipping.")
        return

    log("Fetching GND property registry")

    run_command(
        [
            sys.executable,
            str(script),
        ]
    )


def fetch_vocab_labels_if_needed(force: bool = False) -> None:
    """
    Fetches GND vocabulary labels if missing.
    """

    vocab_file = Path("config/gnd_vocab_labels.json")

    if vocab_file.exists() and not force:
        log("GND vocabulary labels already exist. Skipping.")
        return

    script = Path("scripts/fetch_gnd_vocab_labels.py")

    if not script.exists():
        log("GND vocabulary label fetch script not found. Skipping.")
        return

    log("Fetching GND vocabulary labels")

    run_command(
        [
            sys.executable,
            str(script),
        ]
    )


def build_full_index(limit: int | None = None) -> None:
    command = [
        sys.executable,
        "scripts/index_all_gnd_lds.py",
    ]

    if limit is not None:
        command.extend(["--limit", str(limit)])

    run_command(command)


def initial_setup_required() -> bool:
    state = load_state()

    if not state.get("initialized"):
        return True

    if not index_exists(INDEX_NAME):
        return True

    if get_index_count(INDEX_NAME) == 0:
        return True

    return False


def write_initialized_state() -> None:
    count = get_index_count(INDEX_NAME)

    state = {
        "initialized": True,
        "active_index": INDEX_NAME,
        "last_full_import": timestamp(),
        "document_count": count,
        "sources": {
            source: {
                "downloaded": True,
                "indexed": True,
            }
            for source in REQUIRED_SOURCES
        },
    }

    write_state(state)

    log(f"State written. Indexed documents: {count:,}")


def check_only() -> None:
    ensure_directories()
    wait_for_opensearch()

    state = load_state()
    exists = index_exists(INDEX_NAME)
    count = get_index_count(INDEX_NAME) if exists else 0

    log("Bootstrap check-only result:")
    log(f"State initialized: {state.get('initialized', False)}")
    log(f"Index exists: {exists}")
    log(f"Index count: {count:,}")

    if initial_setup_required():
        log("Initial setup is required.")
    else:
        log("Initial setup is not required.")

def download_entityfacts_if_needed() -> None:
    entityfacts_file = Path("data/raw/authorities-gnd_entityfacts.ndjson.gz")

    if entityfacts_file.exists():
        log("EntityFacts dump already exists. Skipping download.")
        return

    log("Downloading EntityFacts dump")

    run_command(
        [
            sys.executable,
            "-m",
            "importer.download_gnd_lds",
            "--source",
            "entityfacts",
        ]
    )

def index_entityfacts_enrichment(limit: int | None = None) -> None:
    if not GND_INDEX_ENTITYFACTS:
        log("EntityFacts enrichment disabled. Skipping.")
        return

    command = [
        sys.executable,
        "-m",
        "indexer.index_entityfacts",
    ]

    if GND_ENTITYFACTS_ONLY_TYPE:
        command.extend(["--only-type", GND_ENTITYFACTS_ONLY_TYPE])

    if limit is not None:
        command.extend(["--limit", str(limit)])

    log("Starting EntityFacts enrichment")
    run_command(command)
    log("Finished EntityFacts enrichment")


def run_init(limit: int | None = None) -> None:
    ensure_directories()
    wait_for_opensearch()

    log("Starting initial GND setup")

    download_missing_gnd_files()
    download_entityfacts_if_needed()
    fetch_property_registry_if_needed()
    fetch_vocab_labels_if_needed()
    build_full_index(limit=limit)
    index_entityfacts_enrichment(limit=limit)
    write_initialized_state()

    log("Initial GND setup completed")


def run_auto(limit: int | None = None) -> None:
    ensure_directories()
    wait_for_opensearch()

    if GND_FORCE_REINDEX:
        log("GND_FORCE_REINDEX=true. Rebuilding full GND index.")
        download_missing_gnd_files()
        fetch_property_registry_if_needed()
        fetch_vocab_labels_if_needed()
        build_full_index(limit=limit)
        write_initialized_state()
        log("Forced full reindex completed.")
        return

    if initial_setup_required():
        log("Initial setup required. Running setup.")
        run_init(limit=limit)
    else:
        log("GND index already initialized. Skipping full setup.")
        state = load_state()
        log(f"Last full import: {state.get('last_full_import')}")
        log(f"Document count in state: {state.get('document_count')}")
        log(f"Current OpenSearch count: {get_index_count(INDEX_NAME):,}")
        log("Update check not yet implemented.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap local GND data and OpenSearch index."
    )

    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check bootstrap state, do not initialize.",
    )

    parser.add_argument(
        "--init",
        action="store_true",
        help="Run initial setup explicitly.",
    )

    parser.add_argument(
        "--auto",
        action="store_true",
        help="Run setup only if required.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional per-source indexing limit for testing.",
    )

    args = parser.parse_args()

    if args.check_only:
        check_only()
        return

    if args.init:
        run_init(limit=args.limit)
        return

    if args.auto:
        run_auto(limit=args.limit)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
