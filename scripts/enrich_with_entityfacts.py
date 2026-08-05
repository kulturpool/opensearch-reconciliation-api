import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


LOG_DIR = Path("data/logs")
LOG_FILE = LOG_DIR / "entityfacts_enrichment.log"


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_directories() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def log(message: str) -> None:
    ensure_directories()

    line = f"[{timestamp()}] {message}"
    print(line)

    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(line + "\n")


def run_command(command: list[str]) -> None:
    log("RUN " + " ".join(command))
    subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich the existing GND OpenSearch index with EntityFacts. This never recreates the index."
    )

    parser.add_argument(
        "--only-type",
        default=None,
        help="Only enrich one normalized GND type, for example Family.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of normalized EntityFacts records to import.",
    )

    parser.add_argument(
        "--raw-limit",
        type=int,
        default=None,
        help="Maximum number of raw EntityFacts records to read.",
    )

    parser.add_argument(
        "--chunk-size",
        type=int,
        default=None,
        help="OpenSearch bulk chunk size.",
    )

    args = parser.parse_args()

    command = [
        sys.executable,
        "-m",
        "indexer.index_entityfacts",
    ]

    if args.only_type:
        command.extend(["--only-type", args.only_type])

    if args.limit is not None:
        command.extend(["--limit", str(args.limit)])

    if args.raw_limit is not None:
        command.extend(["--raw-limit", str(args.raw_limit)])

    if args.chunk_size is not None:
        command.extend(["--chunk-size", str(args.chunk_size)])

    log("Starting EntityFacts enrichment")
    log("This operation does not recreate or delete the gnd index.")

    run_command(command)

    log("Finished EntityFacts enrichment")


if __name__ == "__main__":
    main()