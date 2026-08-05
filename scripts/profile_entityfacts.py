import argparse
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


DEFAULT_INPUT = Path("data/raw/authorities-gnd_entityfacts.ndjson.gz")


def as_list(value: Any) -> list:
    if value is None:
        return []

    if isinstance(value, list):
        return value

    return [value]


def normalize_type(value: Any) -> str:
    value = str(value or "").strip()

    if "#" in value:
        value = value.split("#")[-1]

    if "/" in value:
        value = value.rstrip("/").split("/")[-1]

    return value.lower()


def extract_types(record: dict[str, Any]) -> list:
    raw_types = record.get("@type") or record.get("type") or []

    return [
        normalize_type(value)
        for value in as_list(raw_types)
        if value
    ]


def compact_value_preview(value: Any, max_length: int = 120) -> str:
    """
    Produces a short preview value for reporting.
    """

    if value is None:
        return ""

    if isinstance(value, dict):
        for key in ["preferredName", "label", "name", "@id", "id"]:
            if key in value:
                return compact_value_preview(value[key], max_length=max_length)

        return compact_value_preview(str(value), max_length=max_length)

    if isinstance(value, list):
        if not value:
            return ""

        return compact_value_preview(value[0], max_length=max_length)

    text = str(value)

    if len(text) > max_length:
        return text[:max_length] + "..."

    return text


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Profile all @type values and fields in DNB GND EntityFacts NDJSON."
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Path to authorities-gnd_entityfacts.ndjson.gz",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of records to inspect. Default: all records.",
    )

    parser.add_argument(
        "--examples-per-type",
        type=int,
        default=3,
        help="Number of example records to keep per type.",
    )

    parser.add_argument(
        "--field-sample-limit",
        type=int,
        default=20,
        help="Number of sample values to collect per type/field.",
    )

    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Input file not found: {args.input}")

    type_counts: Counter[str] = Counter()
    field_counts_by_type: dict[str, Counter[str]] = defaultdict(Counter)
    examples_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    field_examples_by_type: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

    total = 0
    invalid_json = 0
    records_without_type = 0

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

            if not types:
                records_without_type += 1
                types = ["__missing_type__"]

            for entity_type in types:
                type_counts[entity_type] += 1

                if len(examples_by_type[entity_type]) < args.examples_per_type:
                    examples_by_type[entity_type].append(record)

                for key, value in record.items():
                    field_counts_by_type[entity_type][key] += 1

                    samples = field_examples_by_type[entity_type][key]

                    if len(samples) < args.field_sample_limit:
                        preview = compact_value_preview(value)

                        if preview and preview not in samples:
                            samples.append(preview)

            if args.limit is not None and total >= args.limit:
                break

    print()
    print("=" * 100)
    print("ENTITYFACTS TYPE PROFILE")
    print("=" * 100)
    print(f"Records inspected:      {total:,}")
    print(f"Invalid JSON lines:     {invalid_json:,}")
    print(f"Records without type:   {records_without_type:,}")

    print()
    print("=" * 100)
    print("TYPE COUNTS")
    print("=" * 100)

    for entity_type, count in type_counts.most_common():
        print(f"{entity_type}: {count:,}")

    print()
    print("=" * 100)
    print("FIELDS BY TYPE")
    print("=" * 100)

    for entity_type, count in type_counts.most_common():
        print()
        print("-" * 100)
        print(f"TYPE: {entity_type} ({count:,} records)")
        print("-" * 100)

        for field, field_count in field_counts_by_type[entity_type].most_common(50):
            percent = (field_count / count) * 100 if count else 0
            print(f"{field}: {field_count:,} ({percent:.1f}%)")

            samples = field_examples_by_type[entity_type].get(field, [])

            for sample in samples[:3]:
                print(f"  sample: {sample}")

    print()
    print("=" * 100)
    print("EXAMPLE RECORDS BY TYPE")
    print("=" * 100)

    for entity_type, examples in examples_by_type.items():
        print()
        print("#" * 100)
        print(f"TYPE: {entity_type}")
        print("#" * 100)

        for index, example in enumerate(examples, start=1):
            print()
            print(f"Example {index}")
            print(json.dumps(example, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()