import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path to allow imports from config
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DATA_DIR

SOURCES = [
    "sachbegriff",
    "geografikum",
    "werk",
    "koerperschaft",
    "kongress",
    "person",
]

STATE_DIR = DATA_DIR / "state"
LOG_DIR = DATA_DIR / "logs"
IMPORT_LOG = LOG_DIR / "index_all_gnd_lds.log"


def ensure_directories() -> None:
    """
    Ensures that local runtime directories exist.
    The data directory is intentionally not tracked by git,
    so it must be created at runtime.
    """
    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / "raw").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "processed").mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def log(message: str) -> None:
    line = f"[{timestamp()}] {message}"
    print(line, flush=True)

    with IMPORT_LOG.open("a", encoding="utf-8") as file:
        file.write(line + "\n")


def run_command(command: list[str]) -> None:
    log("RUN " + " ".join(command))
    subprocess.run(command, check=True)


def index_source(
    source: str,
    index_name: str,
    recreate: bool = False,
    limit: int | None = None,
    raw_limit: int | None = None,
    chunk_size: int | None = None,
) -> None:
    command = [
        sys.executable,
        "-m",
        "indexer.index_gnd_lds",
        "--source",
        source,
        "--index",
        index_name,
    ]

    if recreate:
        command.append("--recreate")

    if limit is not None:
        command.extend(["--limit", str(limit)])

    if raw_limit is not None:
        command.extend(["--raw-limit", str(raw_limit)])

    if chunk_size is not None:
        command.extend(["--chunk-size", str(chunk_size)])

    run_command(command)


def index_entityfacts(
    index_name: str,
    limit: int | None = None,
    raw_limit: int | None = None,
    chunk_size: int | None = None,
) -> None:
    command = [
        sys.executable,
        "-m",
        "indexer.index_entityfacts",
        "--index",
        index_name,
    ]

    if limit is not None:
        command.extend(["--limit", str(limit)])

    if raw_limit is not None:
        command.extend(["--raw-limit", str(raw_limit)])

    if chunk_size is not None:
        command.extend(["--chunk-size", str(chunk_size)])

    run_command(command)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Index all DNB GND LDS sources into an OpenSearch index."
    )

    parser.add_argument(
        "--index",
        default="gnd",
        help="OpenSearch index name. Defaults to gnd.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional normalized record limit per source for testing.",
    )

    parser.add_argument(
        "--raw-limit",
        type=int,
        default=None,
        help="Optional raw record/chunk limit per source for testing.",
    )

    parser.add_argument(
        "--chunk-size",
        type=int,
        default=None,
        help="Optional OpenSearch bulk chunk size.",
    )

    parser.add_argument(
        "--skip-person",
        action="store_true",
        help="Skip the large person source.",
    )

    parser.add_argument(
        "--skip-entityfacts",
        action="store_true",
        help="Skip EntityFacts enrichment after LDS indexing.",
    )

    args = parser.parse_args()

    ensure_directories()

    log(f"Starting full GND LDS indexing into index '{args.index}'")

    sources = SOURCES.copy()

    if args.skip_person:
        sources = [source for source in sources if source != "person"]

    first = True

    for source in sources:
        log(f"Indexing source: {source}")

        index_source(
            source=source,
            index_name=args.index,
            recreate=first,
            limit=args.limit,
            raw_limit=args.raw_limit,
            chunk_size=args.chunk_size,
        )

        first = False

    log("Finished full GND LDS indexing")

    if args.skip_entityfacts:
        log("Skipping EntityFacts enrichment")
    else:
        log("Starting EntityFacts enrichment")

        index_entityfacts(
            index_name=args.index,
            limit=args.limit,
            raw_limit=args.raw_limit,
            chunk_size=args.chunk_size,
        )

        log("Finished EntityFacts enrichment")


if __name__ == "__main__":
    main()
