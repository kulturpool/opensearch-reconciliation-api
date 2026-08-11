import argparse
import gzip
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# Add parent directory to path to allow imports from config
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DATA_DIR

DEFAULT_INPUT = DATA_DIR / "raw" / "authorities-gnd_entityfacts.ndjson.gz"


def compact_type(value: str) -> str:
    value = str(value)

    if "#" in value:
        return value.split("#")[-1]

    if "/" in value:
        return value.rstrip("/").split("/")[-1]

    return value


def as_list(value: Any) -> list:
    if value is None:
        return []

    if isinstance(value, list):
        return value

    return [value]


def normalize_type(value: str) -> str:
    value = str(value)

    if "#" in value:
        value = value.split("#")[-1]

    if "/" in value:
        value = value.rstrip("/").split("/")[-1]

    return value.strip().lower()


def extract_types(record: dict[str, Any]) -> list[str]:
    raw_types = record.get("@type") or record.get("type") or []

    return [normalize_type(value) for value in as_list(raw_types) if value]


def record_contains_family_marker(record: dict[str, Any]) -> bool:
    text = json.dumps(record, ensure_ascii=False).lower()

    return "family" in text or "familie" in text or "familien" in text


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect DNB GND EntityFacts NDJSON records."
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Path to authorities-gnd_entityfacts.ndjson.gz",
    )

    parser.add_argument(
        "--only-type",
        default="family",
        help="Only print examples for this normalized type, e.g. family, person, organisation, event, place.",
    )

    parser.add_argument(
        "--examples",
        type=int,
        default=5,
        help="Number of example records to print.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=100000,
        help="Maximum number of records to inspect.",
    )

    parser.add_argument(
        "--search-family-marker",
        action="store_true",
        help="Also print records that contain family/familie/familien anywhere in the JSON.",
    )

    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Input file not found: {args.input}")

    only_type = args.only_type.strip().lower()

    type_counts = Counter()
    printed = 0
    marker_printed = 0
    total = 0
    invalid_json = 0

    with gzip.open(args.input, "rt", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            total += 1

            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                invalid_json += 1
                print(f"[WARN] Invalid JSON at line {line_number}: {error}")
                continue

            types = extract_types(record)

            for entity_type in types:
                type_counts[entity_type] += 1

            if only_type in types and printed < args.examples:
                printed += 1

                print()
                print("=" * 80)
                print(f"Example {printed} for type '{only_type}'")
                print("=" * 80)
                print(json.dumps(record, ensure_ascii=False, indent=2))

            if (
                args.search_family_marker
                and marker_printed < args.examples
                and record_contains_family_marker(record)
                and only_type not in types
            ):
                marker_printed += 1

                print()
                print("=" * 80)
                print(
                    f"Possible family-related record by marker search {marker_printed}"
                )
                print("=" * 80)
                print(json.dumps(record, ensure_ascii=False, indent=2))

            if total >= args.limit:
                break

    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Records inspected: {total:,}")
    print(f"Invalid JSON lines: {invalid_json:,}")
    print(f"Examples printed for type '{only_type}': {printed:,}")

    if args.search_family_marker:
        print(f"Family marker examples printed: {marker_printed:,}")

    print()
    print("Top types:")

    for entity_type, count in type_counts.most_common(50):
        print(f"{entity_type}: {count:,}")


if __name__ == "__main__":
    main()
