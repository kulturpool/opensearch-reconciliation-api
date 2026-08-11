import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from opensearchpy import OpenSearch
from opensearchpy.exceptions import (
    ConnectionError as OpenSearchConnectionError,
)
from opensearchpy.exceptions import (
    OpenSearchException,
    TransportError,
)

from config import (
    DATA_DIR,
    GND_ENTITYFACTS_ONLY_TYPE,
    GND_FORCE_REINDEX,
    GND_INDEX_ENTITYFACTS,
    INDEX_NAME,
    OPENSEARCH_HOST,
    OPENSEARCH_PORT,
)
from scripts.index_build_state import (
    acquire_index_lock,
    index_state_complete,
    mark_index_build_complete,
    mark_index_build_failed,
    mark_index_build_started,
    read_index_state,
    release_index_lock,
)
from scripts.opensearch_index_admin import (
    cleanup_incomplete_build_index,
    opensearch_index_exists_or_alias_exists,
    validate_built_index,
)

RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
STATE_DIR = DATA_DIR / "state"
LOG_DIR = DATA_DIR / "logs"
STATE_FILE = STATE_DIR / "gnd_state.json"
BOOTSTRAP_LOG = LOG_DIR / "bootstrap_gnd.log"

REQUIRED_SOURCES = [
    "sachbegriff",
    "geografikum",
    "werk",
    "koerperschaft",
    "kongress",
    "person",
]


def timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


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
    print(line, flush=True)

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


def wait_for_opensearch(timeout_seconds: int = 600) -> None:
    """
    Waits until OpenSearch is reachable.
    """
    log("Waiting for OpenSearch...")

    client = get_opensearch_client()
    start = time.time()
    last_error: BaseException | None = None

    while True:
        try:
            info = client.info()
            version = info.get("version", {}).get("number")
            log(f"OpenSearch is available. Version: {version}")
            return

        except (
            OpenSearchConnectionError,
            TransportError,
            OpenSearchException,
            OSError,
        ) as error:
            last_error = error

            if time.time() - start > timeout_seconds:
                raise RuntimeError(
                    f"OpenSearch did not become available in time. Last error: {last_error}"
                ) from error

            time.sleep(3)


def index_exists(index_name: str = INDEX_NAME) -> bool:
    client = get_opensearch_client()

    return opensearch_index_exists_or_alias_exists(
        client=client,
        name=index_name,
    )


def get_index_count(index_name: str = INDEX_NAME) -> int:
    client = get_opensearch_client()

    if not opensearch_index_exists_or_alias_exists(client=client, name=index_name):
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


def download_entityfacts_if_needed() -> None:
    entityfacts_file = DATA_DIR / "raw" / "authorities-gnd_entityfacts.ndjson.gz"

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
    """
    Builds the full LDS index.

    This currently indexes directly into INDEX_NAME. The completion marker is
    only written after this step and EntityFacts enrichment have both succeeded.
    """
    command = [
        sys.executable,
        "scripts/index_all_gnd_lds.py",
    ]

    if limit is not None:
        command.extend(["--limit", str(limit)])

    run_command(command)


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


def validate_current_index(limit: int | None = None) -> dict[str, int]:
    """
    Validates the index after a full build.

    For test runs with --limit, thresholds are relaxed so small developer
    imports do not fail validation.
    """
    client = get_opensearch_client()

    if limit is not None:
        return validate_built_index(
            client=client,
            index_name=INDEX_NAME,
            minimum_documents=1,
            minimum_family_records=0,
        )

    return validate_built_index(
        client=client,
        index_name=INDEX_NAME,
    )


def initial_setup_required() -> bool:
    if GND_FORCE_REINDEX:
        log("Force reindex requested.")
        return True

    if not index_state_complete():
        log("Index state is incomplete or missing. Full reindex required.")
        return True

    client = get_opensearch_client()

    if not opensearch_index_exists_or_alias_exists(client=client, name=INDEX_NAME):
        log(f"OpenSearch index or alias '{INDEX_NAME}' missing. Full reindex required.")
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
        "entityfacts": {
            "downloaded": True,
            "indexed": GND_INDEX_ENTITYFACTS,
        },
    }

    write_state(state)
    log(f"State written. Indexed documents: {count:,}")


def check_only() -> None:
    ensure_directories()
    wait_for_opensearch()

    state = load_state()
    index_build_state = read_index_state()
    exists = index_exists(INDEX_NAME)
    count = get_index_count(INDEX_NAME) if exists else 0

    log("Bootstrap check-only result:")
    log(f"State initialized: {state.get('initialized', False)}")
    log(f"Index build status: {index_build_state.get('status')}")
    log(f"Index exists or alias exists: {exists}")
    log(f"Index count: {count:,}")

    if initial_setup_required():
        log("Initial setup is required.")
    else:
        log("Initial setup is not required.")


def run_init(limit: int | None = None) -> None:
    """
    Runs a protected full setup.

    A full index is considered usable only after:
    - LDS indexing completed
    - EntityFacts enrichment completed, if enabled
    - index validation passed
    - index_state.json status is complete
    - index_complete.marker exists

    If the container is interrupted, no completion marker is written. The next
    startup will therefore trigger a new full setup.
    """
    ensure_directories()
    wait_for_opensearch()

    log("Starting initial GND setup")

    acquire_index_lock()

    try:
        client = get_opensearch_client()

        cleanup_incomplete_build_index(
            client=client,
            state=read_index_state(),
        )

        mark_index_build_started(INDEX_NAME)

        download_missing_gnd_files()
        download_entityfacts_if_needed()
        fetch_property_registry_if_needed()
        fetch_vocab_labels_if_needed()

        build_full_index(limit=limit)
        index_entityfacts_enrichment(limit=limit)

        validation = validate_current_index(limit=limit)

        mark_index_build_complete(
            active_index=INDEX_NAME,
            document_count=validation["document_count"],
            family_count=validation.get("family_count"),
            entityfacts_count=validation.get("entityfacts_count"),
        )

        write_initialized_state()

        log("Initial GND setup completed")

    except (
        RuntimeError,
        subprocess.CalledProcessError,
        OSError,
        OpenSearchException,
    ) as error:
        mark_index_build_failed(str(error))
        log(f"Initial GND setup failed: {error}")
        raise

    finally:
        release_index_lock()


def run_auto(limit: int | None = None) -> None:
    ensure_directories()
    wait_for_opensearch()

    if initial_setup_required():
        log("Initial setup required. Running setup.")
        run_init(limit=limit)
        return

    log("GND index already initialized. Skipping full setup.")

    state = load_state()
    index_build_state = read_index_state()

    log(f"Last full import: {state.get('last_full_import')}")
    log(f"Document count in state: {state.get('document_count')}")
    log(f"Index build status: {index_build_state.get('status')}")
    log(f"Current OpenSearch count: {get_index_count(INDEX_NAME):,}")


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
