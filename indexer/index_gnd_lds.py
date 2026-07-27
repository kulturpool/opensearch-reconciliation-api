import argparse
import gzip
from pathlib import Path
from typing import Any, Iterator

import ijson
from opensearchpy import OpenSearch, helpers

from importer.download_gnd_lds import GND_LDS_SOURCES, get_filename_from_url
from importer.normalize_gnd_lds import normalize_gnd_lds_record


DEFAULT_INDEX_NAME = "gnd"
DEFAULT_RAW_DIR = "data/raw"


def get_opensearch_client() -> OpenSearch:
    """
    Creates an OpenSearch client for the local DevContainer setup.
    """

    return OpenSearch(
        hosts=[{"host": "opensearch", "port": 9200}],
        http_compress=True,
        use_ssl=False,
        verify_certs=False,
        ssl_show_warn=False,
    )
# Again another OpenSearch client gets created, check if this is necessary or if we can reuse the exisiting one(s)

def create_index(
    client: OpenSearch,
    index_name: str,
    recreate: bool = False,
) -> None:
    """
    Creates the GND OpenSearch index.

    If recreate=True, the existing index will be deleted first.
    """

    if client.indices.exists(index=index_name):
        if recreate:
            print(f"[INDEX] Deleting existing index: {index_name}")
            client.indices.delete(index=index_name)
        else:
            print(f"[INDEX] Index already exists: {index_name}")
            return

    mapping = {
        "settings": {
            "index": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "refresh_interval": "30s",
            },
            "analysis": {
                "analyzer": {
                    "gnd_text_analyzer": {
                        "type": "standard",
                        "stopwords": "_none_",
                    }
                },
                "normalizer": {
                    "lowercase_normalizer": {
                        "type": "custom",
                        "filter": ["lowercase"],
                    }
                },
            },
        },
        "mappings": {
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
                        },
                        "lowercase": {
                            "type": "keyword",
                            "normalizer": "lowercase_normalizer",
                        },
                    },
                },
                "variantName": {
                    "type": "text",
                    "analyzer": "gnd_text_analyzer",
                    "fields": {
                        "keyword": {
                            "type": "keyword",
                        },
                        "lowercase": {
                            "type": "keyword",
                            "normalizer": "lowercase_normalizer",
                        },
                    },
                },
                "type": {
                    "type": "keyword",
                },
                "dateOfBirth": {
                    "type": "keyword",
                },
                "dateOfDeath": {
                    "type": "keyword",
                },
                "professionOrOccupation": {
                    "type": "text",
                    "analyzer": "gnd_text_analyzer",
                },
                "placeOfBirth": {
                    "type": "text",
                    "analyzer": "gnd_text_analyzer",
                },
                "placeOfDeath": {
                    "type": "text",
                    "analyzer": "gnd_text_analyzer",
                },
                "source": {
                    "type": "keyword",
                },

                "availableProperties": {
                    "type": "keyword"
                },
                "propertiesFlat": {
                    "type": "nested",
                    "properties": {
                        "id": {
                            "type": "keyword"
                        },
                        "value": {
                            "type": "text",
                            "fields": {
                                "keyword": {
                                    "type": "keyword",
                                    "ignore_above": 1024
                                }
                            }
                        }
                    }
                }
            }
        },
    }

    print(f"[INDEX] Creating index: {index_name}")
    client.indices.create(index=index_name, body=mapping)


def resolve_input_file(
    source: str,
    raw_dir: str,
    input_file: str | None = None,
) -> Path:
    """
    Resolves the local input file path.

    If --input is supplied, it is used directly.
    Otherwise the filename is derived from the configured DNB source URL.
    """

    if input_file:
        return Path(input_file)

    if source not in GND_LDS_SOURCES:
        valid_sources = ", ".join(sorted(GND_LDS_SOURCES.keys()))
        raise ValueError(
            f"Unknown source: {source}. Valid sources: {valid_sources}"
        )

    url = GND_LDS_SOURCES[source]
    filename = get_filename_from_url(url)

    return Path(raw_dir) / filename


def iter_gnd_lds_records(
    input_path: Path,
    raw_limit: int | None = None,
) -> Iterator[dict[str, Any]]:
    """
    Streams raw records from a DNB GND LDS JSON-LD gzip file.

    The inspected file structure is a top-level array of arrays:

    [
      [
        {...},
        {...}
      ],
      [
        {...}
      ]
    ]

    Therefore ijson.items(file, "item") yields chunks/lists,
    and we flatten them here.

    raw_limit limits the number of raw JSON-LD records read, not the number
    of indexed GND entities.
    """

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    yielded = 0

    with gzip.open(input_path, "rb") as file:
        for chunk_number, chunk in enumerate(ijson.items(file, "item"), start=1):
            if not isinstance(chunk, list):
                continue

            for record in chunk:
                if not isinstance(record, dict):
                    continue

                yield record
                yielded += 1

                if raw_limit is not None and yielded >= raw_limit:
                    return

            if chunk_number % 100 == 0:
                print(f"[STREAM] Processed chunks: {chunk_number:,}")

def iter_gnd_lds_chunks(
    input_path: Path,
    raw_limit: int | None = None,
):
    """
    Streams chunks from the DNB GND LDS JSON-LD gzip file.

    Each top-level item is a list of JSON-LD records. We build a map of
    blank nodes for each chunk so references such as _:node... can be resolved.
    """

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    raw_seen = 0

    with gzip.open(input_path, "rb") as file:
        for chunk_number, chunk in enumerate(ijson.items(file, "item"), start=1):
            if not isinstance(chunk, list):
                continue

            node_map = {
                record.get("@id"): record
                for record in chunk
                if isinstance(record, dict)
                and isinstance(record.get("@id"), str)
            }

            records = []

            for record in chunk:
                if not isinstance(record, dict):
                    continue

                records.append(record)
                raw_seen += 1

                if raw_limit is not None and raw_seen >= raw_limit:
                    yield records, node_map
                    return

            yield records, node_map

            if chunk_number % 100 == 0:
                print(f"[STREAM] Processed chunks: {chunk_number:,}")

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

    for records, node_map in iter_gnd_lds_chunks(
        input_path=input_path,
        raw_limit=raw_limit,
    ):
        for raw_record in records:
            raw_count += 1

            normalized = normalize_gnd_lds_record(
                raw_record,
                source_key=source_key,
                node_map=node_map,
            )

            if normalized is None:
                skipped_count += 1
                continue

            normalized_count += 1

            if normalized_count % 10_000 == 0:
                print(
                    f"[NORMALIZE] raw={raw_count:,} "
                    f"indexed={normalized_count:,} "
                    f"skipped={skipped_count:,}"
                )

            yield {
                "_index": index_name,
                "_id": normalized["id"],
                "_source": normalized,
            }

            if index_limit is not None and normalized_count >= index_limit:
                break

        if index_limit is not None and normalized_count >= index_limit:
            break

    print()
    print("[NORMALIZE] Finished")
    print(f"[NORMALIZE] Raw records seen:     {raw_count:,}")
    print(f"[NORMALIZE] Normalized/indexed:   {normalized_count:,}")
    print(f"[NORMALIZE] Skipped:              {skipped_count:,}")


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

    print(f"[INDEX] Input file: {input_path}")
    print(f"[INDEX] Target index: {index_name}")
    print(f"[INDEX] Index limit: {index_limit if index_limit else 'none'}")
    print(f"[INDEX] Raw limit:   {raw_limit if raw_limit else 'none'}")
    print()

    actions = generate_bulk_actions(
        input_path=input_path,
        index_name=index_name,
        source_key=source_key,
        index_limit=index_limit,
        raw_limit=raw_limit,
    )

    success_count, errors = helpers.bulk(
        client,
        actions,
        chunk_size=chunk_size,
        request_timeout=180,
        raise_on_error=False,
        stats_only=False,
    )

    client.indices.refresh(index=index_name)

    print()
    print(f"[INDEX] Successfully indexed: {success_count:,}")

    if errors:
        print(f"[INDEX] Errors: {len(errors):,}")
        print("[INDEX] First errors:")
        for error in errors[:5]:
            print(error)


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
                "refresh_interval": "1s"
            }
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Index DNB GND LDS JSON-LD dumps into OpenSearch."
    )

    parser.add_argument(
        "--source",
        choices=list(GND_LDS_SOURCES.keys()),
        default="sachbegriff",
        help="GND LDS source key. Default: sachbegriff",
    )

    parser.add_argument(
        "--input",
        default=None,
        help="Optional explicit input .jsonld.gz file.",
    )

    parser.add_argument(
        "--raw-dir",
        default=DEFAULT_RAW_DIR,
        help=f"Directory containing downloaded raw files. Default: {DEFAULT_RAW_DIR}",
    )

    parser.add_argument(
        "--index",
        default=DEFAULT_INDEX_NAME,
        help=f"OpenSearch index name. Default: {DEFAULT_INDEX_NAME}",
    )

    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete and recreate the index before indexing.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of successfully indexed GND records for testing.",
    )

    parser.add_argument(
        "--raw-limit",
        type=int,
        default=None,
        help="Limit number of raw JSON-LD records read. Mainly useful for debugging.",
    )

    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1000,
        help="OpenSearch bulk chunk size. Default: 1000",
    )

    args = parser.parse_args()

    input_path = resolve_input_file(
        source=args.source,
        raw_dir=args.raw_dir,
        input_file=args.input,
    )

    client = get_opensearch_client()

    print("[CHECK] Connecting to OpenSearch...")
    info = client.info()
    print(f"[CHECK] OpenSearch version: {info.get('version', {}).get('number')}")
    print()

    create_index(
        client=client,
        index_name=args.index,
        recreate=args.recreate,
    )

    try:
        index_gnd_lds(
            client=client,
            input_path=input_path,
            index_name=args.index,
            source_key=args.source,
            index_limit=args.limit,
            raw_limit=args.raw_limit,
            chunk_size=args.chunk_size,
        )
    finally:
        restore_refresh_interval(
            client=client,
            index_name=args.index,
        )

    print()
    print("[DONE]")


if __name__ == "__main__":
    main()