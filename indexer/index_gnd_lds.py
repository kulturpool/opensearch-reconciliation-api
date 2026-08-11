import argparse
import gzip
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

# Add parent directory to path to allow imports from config
sys.path.insert(0, str(Path(__file__).parent.parent))

import ijson
from opensearchpy import OpenSearch, helpers

from config import INDEX_NAME, OPENSEARCH_HOST, OPENSEARCH_PORT
from importer.download_gnd_lds import GND_LDS_SOURCES, get_filename_from_url
from importer.normalize_gnd_lds import normalize_gnd_lds_record

DEFAULT_RAW_DIR = "data/raw"


INDEX_SETTINGS: dict[str, Any] = {
    "settings": {
        "index": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "refresh_interval": "-1",
        },
        "analysis": {
            "analyzer": {
                "gnd_text_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": [
                        "lowercase",
                        "asciifolding",
                    ],
                }
            }
        },
    },
    "mappings": {
        "dynamic": True,
        "properties": {
            "id": {
                "type": "keyword",
            },
            "uri": {
                "type": "keyword",
            },
            "preferredName": {
                "type": "text",
                "analyzer": "gnd_text_analyzer",
                "fields": {
                    "keyword": {
                        "type": "keyword",
                        "ignore_above": 512,
                    }
                },
            },
            "variantName": {
                "type": "text",
                "analyzer": "gnd_text_analyzer",
                "fields": {
                    "keyword": {
                        "type": "keyword",
                        "ignore_above": 512,
                    }
                },
            },
            "type": {
                "type": "keyword",
            },
            "source": {
                "type": "keyword",
            },
            "sources": {
                "type": "keyword",
            },
            "availableProperties": {
                "type": "keyword",
            },
            "dateOfBirth": {
                "type": "keyword",
            },
            "dateOfDeath": {
                "type": "keyword",
            },
            "dateOfEstablishment": {
                "type": "keyword",
            },
            "dateOfTermination": {
                "type": "keyword",
            },
            "dateOfProduction": {
                "type": "keyword",
            },
            "dateOfPublication": {
                "type": "keyword",
            },
            "propertiesFlat": {
                "type": "nested",
                "properties": {
                    "id": {
                        "type": "keyword",
                    },
                    "value": {
                        "type": "text",
                        "analyzer": "gnd_text_analyzer",
                        "fields": {
                            "keyword": {
                                "type": "keyword",
                                "ignore_above": 1024,
                            }
                        },
                    },
                },
            },
            "entityfactsEnriched": {
                "type": "boolean",
            },
            "entityfactsType": {
                "type": "keyword",
            },
            "oaiUpdated": {
                "type": "boolean",
            },
            "lastUpdateAction": {
                "type": "keyword",
            },
            "deleted": {
                "type": "boolean",
            },
            "deprecated": {
                "type": "boolean",
            },
        },
    },
}


JSONLD_ITEM_PATHS = [
    "item.item",  # For nested array structure: [[{...}, {...}], [...], ...]
    "@graph.item",  # For @graph-wrapped structure: {"@graph": [{...}]}
    "item",  # For simple array structure: [{...}, {...}]
]


def get_opensearch_client() -> OpenSearch:
    """
    Creates an OpenSearch client for the local Docker/DevContainer setup.
    """
    return OpenSearch(
        hosts=[{"host": OPENSEARCH_HOST, "port": OPENSEARCH_PORT}],
        http_compress=True,
        use_ssl=False,
        verify_certs=False,
        ssl_show_warn=False,
    )


def create_index(
    client: OpenSearch,
    index_name: str,
    recreate: bool = False,
) -> None:
    """
    Creates the GND OpenSearch index.

    If recreate=True, the given index is deleted first. This only affects the
    concrete index name supplied via --index and never deletes other indices.
    """
    exists = client.indices.exists(index=index_name)

    if exists and recreate:
        print(f"[INDEX] Deleting existing index: {index_name}", flush=True)
        client.indices.delete(index=index_name)
        exists = False

    if exists:
        print(f"[INDEX] Index already exists: {index_name}", flush=True)
        return

    print(f"[INDEX] Creating index: {index_name}", flush=True)
    client.indices.create(
        index=index_name,
        body=INDEX_SETTINGS,
    )


def resolve_input_file(
    source: str,
    raw_dir: str,
    input_file: str | None = None,
) -> Path:
    """
    Resolves the local input file path.
    """
    if input_file:
        return Path(input_file)

    if source not in GND_LDS_SOURCES:
        valid_sources = ", ".join(sorted(GND_LDS_SOURCES.keys()))
        raise ValueError(f"Unknown source '{source}'. Valid sources: {valid_sources}")

    filename = get_filename_from_url(GND_LDS_SOURCES[source])
    return Path(raw_dir) / filename


def iter_items_for_path(
    input_path: Path,
    item_path: str,
    raw_limit: int | None = None,
) -> Iterator[dict[str, Any]]:
    yielded = 0

    with gzip.open(input_path, "rb") as file:
        for item in ijson.items(file, item_path):
            if isinstance(item, dict):
                yielded += 1
                yield item

                if raw_limit is not None and yielded >= raw_limit:
                    return


def iter_gnd_lds_records(
    input_path: Path,
    raw_limit: int | None = None,
) -> Iterator[dict[str, Any]]:
    """
    Streams raw records from a DNB GND LDS JSON-LD gzip file.

    The DNB dumps can be represented as a JSON-LD graph. We first try
    @graph.item and then fall back to top-level item.
    """
    last_error: BaseException | None = None

    for item_path in JSONLD_ITEM_PATHS:
        yielded = 0

        try:
            for item in iter_items_for_path(
                input_path=input_path,
                item_path=item_path,
                raw_limit=raw_limit,
            ):
                yielded += 1
                yield item

            if yielded > 0:
                return

        except ijson.JSONError as error:
            last_error = error
            continue
        except (OSError, EOFError, gzip.BadGzipFile) as error:
            last_error = error
            break

    if last_error:
        raise RuntimeError(
            f"Could not parse input file {input_path}: {last_error}"
        ) from last_error

    raise RuntimeError(
        f"Could not find records in {input_path}. Tried item paths: {JSONLD_ITEM_PATHS}"
    )


def iter_gnd_lds_chunks(
    input_path: Path,
    raw_limit: int | None = None,
):
    """
    Backwards-compatible alias for streaming LDS records.
    """
    yield from iter_gnd_lds_records(
        input_path=input_path,
        raw_limit=raw_limit,
    )


def generate_bulk_actions(
    input_path: Path,
    index_name: str,
    source_key: str,
    index_limit: int | None = None,
    raw_limit: int | None = None,
):
    """
    Generates OpenSearch bulk actions from normalized GND LDS records.
    """
    raw_count = 0
    normalized_count = 0
    skipped_count = 0

    for raw_record in iter_gnd_lds_records(
        input_path=input_path,
        raw_limit=raw_limit,
    ):
        raw_count += 1

        normalized = normalize_gnd_lds_record(
            raw_record,
            source_key=source_key,
        )

        if normalized is None:
            skipped_count += 1
            continue

        gnd_id = normalized.get("id")

        if not gnd_id:
            skipped_count += 1
            continue

        normalized_count += 1

        if normalized_count % 10000 == 0:
            print(
                f"[GND LDS] source={source_key} raw={raw_count:,} "
                f"normalized={normalized_count:,} skipped={skipped_count:,}",
                flush=True,
            )

        yield {
            "_op_type": "index",
            "_index": index_name,
            "_id": gnd_id,
            "_source": normalized,
        }

        if index_limit is not None and normalized_count >= index_limit:
            break

    print()
    print(f"[GND LDS] Finished source:       {source_key}")
    print(f"[GND LDS] Raw records seen:      {raw_count:,}")
    print(f"[GND LDS] Normalized/indexed:    {normalized_count:,}")
    print(f"[GND LDS] Skipped:               {skipped_count:,}")


def index_gnd_lds(
    client: OpenSearch,
    input_path: Path,
    index_name: str,
    source_key: str,
    index_limit: int | None = None,
    raw_limit: int | None = None,
    chunk_size: int = 1000,
) -> None:
    """
    Bulk indexes normalized GND records into OpenSearch.
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    actions = generate_bulk_actions(
        input_path=input_path,
        index_name=index_name,
        source_key=source_key,
        index_limit=index_limit,
        raw_limit=raw_limit,
    )

    success_count = 0
    error_count = 0

    for success, info in helpers.streaming_bulk(
        client=client,
        actions=actions,
        chunk_size=chunk_size,
        request_timeout=120,
        raise_on_error=False,
    ):
        if success:
            success_count += 1
        else:
            error_count += 1
            print("[ERROR]", info, flush=True)

    print(f"[GND LDS] Successfully written: {success_count:,}", flush=True)
    print(f"[GND LDS] Errors:               {error_count:,}", flush=True)

    if error_count > 0:
        raise RuntimeError(
            f"GND LDS indexing for source '{source_key}' completed with {error_count} errors."
        )


def restore_refresh_interval(
    client: OpenSearch,
    index_name: str,
) -> None:
    """
    Restores a more interactive refresh interval after indexing.
    """
    if not client.indices.exists(index=index_name):
        return

    client.indices.put_settings(
        index=index_name,
        body={
            "index": {
                "refresh_interval": "1s",
            }
        },
    )

    client.indices.refresh(index=index_name)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Index DNB GND LDS JSON-LD dumps into OpenSearch."
    )

    parser.add_argument(
        "--source",
        required=True,
        choices=sorted(GND_LDS_SOURCES.keys()),
        help="GND LDS source key to index.",
    )

    parser.add_argument(
        "--index",
        default=INDEX_NAME,
        help="OpenSearch index name.",
    )

    parser.add_argument(
        "--raw-dir",
        default=DEFAULT_RAW_DIR,
        help="Directory containing downloaded raw GND LDS files.",
    )

    parser.add_argument(
        "--input",
        default=None,
        help="Optional explicit input file path.",
    )

    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete and recreate the target index before indexing this source.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of normalized records to index.",
    )

    parser.add_argument(
        "--raw-limit",
        type=int,
        default=None,
        help="Maximum number of raw records to read.",
    )

    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1000,
        help="OpenSearch bulk chunk size.",
    )

    args = parser.parse_args()

    input_path = resolve_input_file(
        source=args.source,
        raw_dir=args.raw_dir,
        input_file=args.input,
    )

    client = get_opensearch_client()

    create_index(
        client=client,
        index_name=args.index,
        recreate=args.recreate,
    )

    index_gnd_lds(
        client=client,
        input_path=input_path,
        index_name=args.index,
        source_key=args.source,
        index_limit=args.limit,
        raw_limit=args.raw_limit,
        chunk_size=args.chunk_size,
    )

    restore_refresh_interval(
        client=client,
        index_name=args.index,
    )


if __name__ == "__main__":
    main()
