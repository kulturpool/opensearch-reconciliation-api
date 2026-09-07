"""
Bootstraps the Getty (AAT) OpenSearch index: downloads the explicit N-Triples
export(s), builds a fresh index, validates it, and atomically switches the
public "getty" alias to point at it.

Mirrors scripts/bootstrap_gnd.py's structure and CLI (--check-only / --init /
--auto / --limit), but with two deliberate differences:

1. Getty has no incremental update source (unlike GND's OAI-PMH harvest), so
   "updating" Getty always means a full rebuild. See scripts/update_getty.py
   and scripts/update_getty_scheduler.py.
2. Getty's public index name is switched via a real alias-swap
   (scripts.opensearch_index_admin.switch_alias), giving zero-downtime
   rebuilds. The very first automated run also handles a one-time migration:
   the "getty" index was originally built manually (Phase 4 of the AAT
   integration) as a plain concrete index, not an alias. That pre-existing,
   healthy index is adopted as-is (see adopt_existing_index_if_healthy())
   instead of being needlessly rebuilt; it is transparently converted to the
   alias-based pattern the next time a full rebuild actually runs.
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Add parent directory to path to allow imports from config
sys.path.insert(0, str(Path(__file__).parent.parent))

from opensearchpy import OpenSearch
from opensearchpy.exceptions import OpenSearchException

from config import (
    DATA_DIR,
    GETTY_FORCE_REINDEX,
    GETTY_INDEX_LOCK_STALE_SECONDS,
    GETTY_INDEX_NAME,
    GETTY_RAW_DIR,
    GETTY_VOCABULARIES,
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
    count_records,
    delete_index_if_exists,
    opensearch_index_exists_or_alias_exists,
    switch_alias,
)

VOCAB = "getty"
BUILD_INDEX_PREFIX = "getty_build_"

STATE_DIR = DATA_DIR / "state"
LOG_DIR = DATA_DIR / "logs"
STATE_FILE = STATE_DIR / "getty_state.json"
BOOTSTRAP_LOG = LOG_DIR / "bootstrap_getty.log"

# ~60,637 AAT concepts were indexed in the Phase 4 one-off build. Relaxed
# well below that so legitimate smaller vocab combinations still pass.
MINIMUM_DOCUMENTS = 10_000


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_index_timestamp() -> str:
    # OpenSearch index names must be lowercase and cannot contain ":" or
    # uppercase letters, so this can't reuse timestamp()'s ISO-8601 format.
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def ensure_directories() -> None:
    for directory in (DATA_DIR, GETTY_RAW_DIR, STATE_DIR, LOG_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def log(message: str) -> None:
    line = f"[{timestamp()}] {message}"
    print(line, flush=True)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with BOOTSTRAP_LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {}

    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def write_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def get_opensearch_client() -> OpenSearch:
    return OpenSearch(
        hosts=[{"host": OPENSEARCH_HOST, "port": OPENSEARCH_PORT}],
        use_ssl=False,
        verify_certs=False,
        ssl_show_warn=False,
    )


def wait_for_opensearch(timeout_seconds: int = 600) -> None:
    client = get_opensearch_client()
    deadline = time.monotonic() + timeout_seconds

    while True:
        try:
            client.info()
            return
        except Exception:
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"OpenSearch not reachable at {OPENSEARCH_HOST}:{OPENSEARCH_PORT} "
                    f"after {timeout_seconds}s"
                )
            log("Waiting for OpenSearch to become reachable...")
            time.sleep(3)


def get_index_count(index_name: str = GETTY_INDEX_NAME) -> int:
    client = get_opensearch_client()

    if not opensearch_index_exists_or_alias_exists(client=client, name=index_name):
        return 0

    return count_records(client=client, index_name=index_name)


def run_command(command: list[str]) -> None:
    log(f"RUN {' '.join(command)}")
    subprocess.run(command, check=True)


def download_getty_sources() -> None:
    for vocab_key in GETTY_VOCABULARIES:
        log(f"Downloading Getty export for vocab: {vocab_key}")
        run_command(
            [
                sys.executable,
                "-m",
                "importer.download_getty",
                "--source",
                vocab_key,
                "--raw-dir",
                str(GETTY_RAW_DIR),
            ]
        )


def build_getty_index(build_index_name: str, limit: int | None = None) -> None:
    for position, vocab_key in enumerate(GETTY_VOCABULARIES):
        command = [
            sys.executable,
            "-m",
            "indexer.index_getty",
            "--vocab",
            vocab_key,
            "--index",
            build_index_name,
            "--raw-dir",
            str(GETTY_RAW_DIR),
        ]

        # Only recreate (i.e. delete-if-exists + create) before the first
        # vocab is indexed. All Getty vocabs share a single index, so
        # recreating again for subsequent vocabs would wipe what was just
        # indexed.
        if position == 0:
            command.append("--recreate")

        if limit is not None:
            command.extend(["--limit", str(limit)])

        run_command(command)


def validate_getty_index(index_name: str, limit: int | None = None) -> dict[str, int]:
    client = get_opensearch_client()
    document_count = count_records(client=client, index_name=index_name)

    minimum_documents = 1 if limit is not None else MINIMUM_DOCUMENTS

    if document_count < minimum_documents:
        raise RuntimeError(
            f"Built Getty index '{index_name}' has suspiciously few documents: "
            f"{document_count}. Expected at least {minimum_documents}."
        )

    return {"document_count": document_count}


def adopt_existing_index_if_healthy(client: OpenSearch) -> bool:
    """
    If "getty" already resolves to a healthy pre-existing index (e.g. the
    Phase 4 one-off manual build) but there is no managed index_state.json
    yet, adopt it in place instead of paying for a full re-download +
    reindex. The next real full rebuild will transparently migrate it to the
    alias-based pattern via switch_alias().
    """
    if not opensearch_index_exists_or_alias_exists(client=client, name=GETTY_INDEX_NAME):
        return False

    document_count = count_records(client=client, index_name=GETTY_INDEX_NAME)

    if document_count < MINIMUM_DOCUMENTS:
        log(
            f"Existing '{GETTY_INDEX_NAME}' index has too few documents "
            f"({document_count}) to adopt as-is. Full build required."
        )
        return False

    log(
        f"Adopting pre-existing '{GETTY_INDEX_NAME}' index "
        f"({document_count:,} documents) without rebuilding. It will be "
        "converted to the alias-based build pattern on the next full rebuild."
    )

    mark_index_build_started(GETTY_INDEX_NAME, vocab=VOCAB)
    mark_index_build_complete(
        active_index=GETTY_INDEX_NAME,
        document_count=document_count,
        vocab=VOCAB,
    )
    write_initialized_state()

    return True


def initial_setup_required(adopt_existing: bool = False) -> bool:
    if GETTY_FORCE_REINDEX:
        log("GETTY_FORCE_REINDEX is set. Full build required.")
        return True

    if index_state_complete(require_entityfacts=False, vocab=VOCAB):
        client = get_opensearch_client()
        if opensearch_index_exists_or_alias_exists(client=client, name=GETTY_INDEX_NAME):
            return False

        log(
            f"OpenSearch index or alias '{GETTY_INDEX_NAME}' missing despite "
            "complete state. Full build required."
        )
        return True

    client = get_opensearch_client()
    if adopt_existing and adopt_existing_index_if_healthy(client=client):
        return False

    log("Getty index state is incomplete or missing. Full build required.")
    return True


def write_initialized_state() -> None:
    count = get_index_count()
    state = {
        "initialized": True,
        "active_index": GETTY_INDEX_NAME,
        "last_full_build": timestamp(),
        "document_count": count,
        "vocabularies": list(GETTY_VOCABULARIES),
    }
    write_state(state)
    log(f"State written. Indexed documents: {count:,}")


def run_full_build(limit: int | None = None) -> None:
    ensure_directories()
    wait_for_opensearch()

    log("Starting Getty full index build")

    acquire_index_lock(vocab=VOCAB, stale_seconds=GETTY_INDEX_LOCK_STALE_SECONDS)

    try:
        client = get_opensearch_client()

        cleanup_incomplete_build_index(
            client=client,
            state=read_index_state(vocab=VOCAB),
            build_index_prefix=BUILD_INDEX_PREFIX,
        )

        build_index_name = f"{BUILD_INDEX_PREFIX}{build_index_timestamp()}"
        mark_index_build_started(build_index_name, vocab=VOCAB)

        download_getty_sources()
        build_getty_index(build_index_name, limit=limit)

        validation = validate_getty_index(build_index_name, limit=limit)

        log(f"Switching '{GETTY_INDEX_NAME}' alias to '{build_index_name}'")
        old_indices = switch_alias(
            client=client,
            new_index=build_index_name,
            alias_name=GETTY_INDEX_NAME,
        )

        for old_index in old_indices:
            if str(old_index).startswith(BUILD_INDEX_PREFIX):
                log(f"Deleting previous Getty build index: {old_index}")
                delete_index_if_exists(client=client, index_name=str(old_index))

        mark_index_build_complete(
            active_index=GETTY_INDEX_NAME,
            document_count=validation["document_count"],
            vocab=VOCAB,
        )

        write_initialized_state()

        log("Getty full index build completed")

    except (RuntimeError, subprocess.CalledProcessError, OSError, OpenSearchException) as error:
        mark_index_build_failed(str(error), vocab=VOCAB)
        log(f"Getty full index build failed: {error}")
        raise

    finally:
        release_index_lock(vocab=VOCAB)


def run_init(limit: int | None = None) -> None:
    log("Running Getty --init (forced full build)")
    run_full_build(limit=limit)


def run_auto(limit: int | None = None) -> None:
    ensure_directories()
    wait_for_opensearch()

    if initial_setup_required(adopt_existing=True):
        log("Initial setup required. Running Getty full build.")
        run_full_build(limit=limit)
        return

    state = load_state()
    log("Getty index already initialized. Skipping full build.")
    log(f"Last full build: {state.get('last_full_build')}")
    log(f"Document count in state: {state.get('document_count')}")
    log(f"Current OpenSearch count: {get_index_count():,}")


def check_only() -> None:
    ensure_directories()
    wait_for_opensearch()

    state = load_state()
    build_state = read_index_state(vocab=VOCAB)
    client = get_opensearch_client()
    exists = opensearch_index_exists_or_alias_exists(client=client, name=GETTY_INDEX_NAME)
    count = count_records(client=client, index_name=GETTY_INDEX_NAME) if exists else 0

    log("Getty bootstrap check-only result:")
    log(f"State initialized: {state.get('initialized', False)}")
    log(f"Index build status: {build_state.get('status')}")
    log(f"Index exists or alias exists: {exists}")
    log(f"Index count: {count:,}")
    log(f"Initial setup required: {initial_setup_required(adopt_existing=False)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap the Getty (AAT) vocabulary OpenSearch index."
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Print current state without performing any build.",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Force a full build, regardless of current state.",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Run a full build only if initial setup is required.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of records indexed per vocab (for testing).",
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
