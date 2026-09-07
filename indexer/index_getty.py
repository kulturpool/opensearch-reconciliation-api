"""
Indexes normalized Getty vocabulary records (see `importer.normalize_getty`)
into OpenSearch.

Structurally mirrors `indexer/index_gnd_lds.py` (same
`create_index`/`generate_bulk_actions`/`index_*`/`restore_refresh_interval`
shape) so the two importers/indexers stay easy to reason about side by side.
"""

import argparse
import sys
from pathlib import Path
from typing import Any

# Add parent directory to path to allow imports from config
sys.path.insert(0, str(Path(__file__).parent.parent))

from opensearchpy import OpenSearch, helpers

from config import GETTY_INDEX_NAME, GETTY_RAW_DIR, OPENSEARCH_HOST, OPENSEARCH_PORT
from importer.getty_vocab_specs import GETTY_VOCAB_SPECS
from importer.normalize_getty import iter_normalized_getty_records

GETTY_INDEX_SETTINGS: dict[str, Any] = {
    "settings": {
        "index": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "refresh_interval": "-1",
        },
        "analysis": {
            "analyzer": {
                "getty_text_analyzer": {
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
            "subjectId": {
                "type": "keyword",
            },
            "vocabulary": {
                "type": "keyword",
            },
            "uri": {
                "type": "keyword",
            },
            "source": {
                "type": "keyword",
            },
            "preferredName": {
                "type": "text",
                "analyzer": "getty_text_analyzer",
                "fields": {
                    "keyword": {
                        "type": "keyword",
                        "ignore_above": 512,
                    }
                },
            },
            "variantName": {
                "type": "text",
                "analyzer": "getty_text_analyzer",
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
            "availableProperties": {
                "type": "keyword",
            },
            "parentString": {
                "type": "text",
                "analyzer": "getty_text_analyzer",
                "fields": {
                    "keyword": {
                        "type": "keyword",
                        "ignore_above": 1024,
                    }
                },
            },
            "parentStringAbbrev": {
                "type": "text",
                "analyzer": "getty_text_analyzer",
                "fields": {
                    "keyword": {
                        "type": "keyword",
                        "ignore_above": 1024,
                    }
                },
            },
            "scopeNote": {
                "type": "text",
                "analyzer": "getty_text_analyzer",
            },
            "broader": {
                "type": "keyword",
            },
            "related": {
                "type": "keyword",
            },
            "notation": {
                "type": "keyword",
            },
            "exactMatch": {
                "type": "keyword",
            },
            # Reference lists into AAT concepts (ULAN nationality/role,
            # TGN place type) - stored as composite "<vocab>/<id>" ids,
            # resolved into reconciled entities at extend time the same way
            # broader/related are, since all Getty vocabs share one index.
            "nationality": {
                "type": "keyword",
            },
            "role": {
                "type": "keyword",
            },
            "placeType": {
                "type": "keyword",
            },
            "biography": {
                "type": "text",
                "analyzer": "getty_text_analyzer",
            },
            # "lat, long" string (ULAN/AAT have none; only TGN populates this).
            "coordinates": {
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
                        "analyzer": "getty_text_analyzer",
                        "fields": {
                            "keyword": {
                                "type": "keyword",
                                "ignore_above": 1024,
                            }
                        },
                    },
                },
            },
        },
    },
}


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
    Creates the Getty OpenSearch index.

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
        body=GETTY_INDEX_SETTINGS,
    )


def generate_bulk_actions(
    raw_dir: Path,
    index_name: str,
    vocab_key: str,
    limit: int | None = None,
):
    """
    Generates OpenSearch bulk actions from normalized Getty records.
    """
    normalized_count = 0

    for normalized in iter_normalized_getty_records(
        raw_dir=raw_dir,
        vocab_key=vocab_key,
        limit=limit,
    ):
        entity_id = normalized.get("id")

        if not entity_id:
            continue

        normalized_count += 1

        if normalized_count % 10000 == 0:
            print(
                f"[GETTY] vocab={vocab_key} indexed={normalized_count:,}",
                flush=True,
            )

        yield {
            "_op_type": "index",
            "_index": index_name,
            "_id": entity_id,
            "_source": normalized,
        }

    print()
    print(f"[GETTY] Finished vocab:       {vocab_key}")
    print(f"[GETTY] Normalized/indexed:   {normalized_count:,}")


def index_getty_vocab(
    client: OpenSearch,
    raw_dir: Path,
    index_name: str,
    vocab_key: str,
    limit: int | None = None,
    chunk_size: int = 1000,
) -> None:
    """
    Bulk indexes normalized Getty records into OpenSearch.
    """
    actions = generate_bulk_actions(
        raw_dir=raw_dir,
        index_name=index_name,
        vocab_key=vocab_key,
        limit=limit,
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

    print(f"[GETTY] Successfully written: {success_count:,}", flush=True)
    print(f"[GETTY] Errors:               {error_count:,}", flush=True)

    if error_count > 0:
        raise RuntimeError(
            f"Getty indexing for vocab '{vocab_key}' completed with {error_count} errors."
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
        description="Index Getty vocabulary explicit exports into OpenSearch."
    )

    parser.add_argument(
        "--vocab",
        required=True,
        choices=sorted(GETTY_VOCAB_SPECS.keys()),
        help="Getty vocabulary key to index.",
    )

    parser.add_argument(
        "--index",
        default=GETTY_INDEX_NAME,
        help="OpenSearch index name.",
    )

    parser.add_argument(
        "--raw-dir",
        default=str(GETTY_RAW_DIR),
        help="Directory containing extracted Getty .nt files.",
    )

    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete and recreate the target index before indexing this vocab.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of normalized records to index.",
    )

    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1000,
        help="OpenSearch bulk chunk size.",
    )

    args = parser.parse_args()

    raw_dir = Path(args.raw_dir)
    client = get_opensearch_client()

    create_index(
        client=client,
        index_name=args.index,
        recreate=args.recreate,
    )

    index_getty_vocab(
        client=client,
        raw_dir=raw_dir,
        index_name=args.index,
        vocab_key=args.vocab,
        limit=args.limit,
        chunk_size=args.chunk_size,
    )

    restore_refresh_interval(
        client=client,
        index_name=args.index,
    )


if __name__ == "__main__":
    main()
