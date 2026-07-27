import argparse
import gzip
import json
from pathlib import Path
from typing import Any


DEFAULT_INPUT = "data/raw/authorities-gnd-sachbegriff_lds.jsonld.gz"


def read_initial_text(path: Path, max_chars: int = 5000) -> str:
    """
    Reads the first characters from a gzip-compressed JSON-LD file.
    This is useful to inspect the top-level JSON structure without
    loading the full file into memory.
    """

    with gzip.open(path, "rt", encoding="utf-8") as file:
        return file.read(max_chars)


def print_file_info(path: Path) -> None:
    """
    Prints basic file information.
    """

    print("=== File info ===")
    print(f"Path: {path}")
    print(f"Exists: {path.exists()}")

    if path.exists():
        size_mb = path.stat().st_size / 1024 / 1024
        print(f"Size: {size_mb:,.2f} MB")

    print()


def print_initial_text(path: Path, max_chars: int) -> None:
    """
    Prints the first characters of the decompressed file.
    """

    print("=== Initial decompressed content ===")
    text = read_initial_text(path, max_chars=max_chars)
    print(text)
    print()
    print("=== End initial content ===")
    print()


def detect_json_start(path: Path) -> None:
    """
    Detects whether the JSON-LD starts with an object or array.
    """

    text = read_initial_text(path, max_chars=1000).lstrip()

    print("=== JSON start detection ===")

    if not text:
        print("No content found.")
    elif text.startswith("{"):
        print("Top-level JSON appears to be an object: {...}")
    elif text.startswith("["):
        print("Top-level JSON appears to be an array: [...]")
    else:
        print(f"Unknown JSON start: {text[:100]!r}")

    print()


def load_small_top_level_object(path: Path, max_chars: int = 2_000_000) -> dict[str, Any] | list[Any] | None:
    """
    Attempts to load a small initial portion as JSON.

    This only works if the file is small enough or if the beginning contains
    a complete JSON document. For large JSON-LD dumps this will often fail,
    which is fine. The streaming inspection below is more important.
    """

    try:
        text = read_initial_text(path, max_chars=max_chars)
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def inspect_with_ijson(path: Path, max_items: int = 3) -> None:
    """
    Uses ijson, if installed, to stream sample records from common JSON-LD paths.

    We try two likely layouts:
    - top-level array: item
    - JSON-LD graph: @graph.item
    """

    print("=== Streaming inspection with ijson ===")

    try:
        import ijson
    except ImportError:
        print("ijson is not installed.")
        print("Install it with:")
        print("  pip install ijson")
        print()
        return

    candidate_paths = [
        "@graph.item",
        "item",
    ]

    for item_path in candidate_paths:
        print(f"Trying ijson path: {item_path}")

        found = 0

        try:
            with gzip.open(path, "rb") as file:
                for item in ijson.items(file, item_path):
                    found += 1
                    print()
                    print(f"--- Sample item {found} from path '{item_path}' ---")
                    print(json.dumps(item, ensure_ascii=False, indent=2)[:5000])

                    if found >= max_items:
                        break

        except Exception as error:
            print(f"Could not parse path '{item_path}': {error}")
            print()
            continue

        if found > 0:
            print()
            print(f"Found {found} sample item(s) with path: {item_path}")
            print("This is likely the path we should use for streaming import.")
            print()
            return

        print(f"No items found with path: {item_path}")
        print()

    print("No sample records found with known paths.")
    print("We need to inspect the JSON-LD structure manually.")
    print()


def inspect_top_level_keys(path: Path) -> None:
    """
    Attempts to detect top-level keys using ijson without loading the full file.
    """

    print("=== Top-level keys via ijson ===")

    try:
        import ijson
    except ImportError:
        print("ijson is not installed.")
        print("Skipping top-level key inspection.")
        print()
        return

    keys = []

    try:
        with gzip.open(path, "rb") as file:
            parser = ijson.parse(file)

            for prefix, event, value in parser:
                if prefix == "" and event == "map_key":
                    keys.append(value)

                if len(keys) >= 20:
                    break

    except Exception as error:
        print(f"Could not inspect top-level keys: {error}")
        print()
        return

    if keys:
        print("Top-level keys:")
        for key in keys:
            print(f"- {key}")
    else:
        print("No top-level keys found.")
        print("The file may be a top-level array.")

    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect a DNB GND LDS JSON-LD gzip file."
    )

    parser.add_argument(
        "--input",
        default=DEFAULT_INPUT,
        help=f"Input .jsonld.gz file. Default: {DEFAULT_INPUT}",
    )

    parser.add_argument(
        "--chars",
        type=int,
        default=3000,
        help="Number of decompressed characters to print from the beginning.",
    )

    parser.add_argument(
        "--samples",
        type=int,
        default=2,
        help="Number of sample records to print with ijson.",
    )

    args = parser.parse_args()

    path = Path(args.input)

    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    print_file_info(path)
    detect_json_start(path)
    inspect_top_level_keys(path)
    print_initial_text(path, max_chars=args.chars)
    inspect_with_ijson(path, max_items=args.samples)


if __name__ == "__main__":
    main()