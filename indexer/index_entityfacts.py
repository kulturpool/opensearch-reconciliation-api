import argparse
import gzip
import json
from pathlib import Path
from typing import Any

from opensearchpy import OpenSearch, helpers

from config import DATA_DIR, INDEX_NAME, OPENSEARCH_HOST, OPENSEARCH_PORT
from importer.normalize_entityfacts import normalize_entityfacts_record

DEFAULT_INPUT = DATA_DIR / "raw" / "authorities-gnd_entityfacts.ndjson.gz"


def get_opensearch_client() -> OpenSearch:
    return OpenSearch(
        hosts=[{"host": OPENSEARCH_HOST, "port": OPENSEARCH_PORT}],
        http_compress=True,
        use_ssl=False,
        verify_certs=False,
        ssl_show_warn=False,
    )


def iter_entityfacts_records(
    input_path: Path,
    raw_limit: int | None = None,
):
    """
    Streams EntityFacts NDJSON records from gzip.
    """
    raw_seen = 0

    with gzip.open(input_path, "rt", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            raw_seen += 1

            try:
                yield json.loads(line)
            except json.JSONDecodeError as error:
                print(f"[WARN] Invalid JSON at line {line_number}: {error}", flush=True)
                continue

            if raw_limit is not None and raw_seen >= raw_limit:
                return


def generate_entityfacts_actions(
    input_path: Path,
    index_name: str,
    only_type: str | None = None,
    index_limit: int | None = None,
    raw_limit: int | None = None,
):
    """
    Generates OpenSearch update/upsert actions from EntityFacts records.
    """
    raw_count = 0
    normalized_count = 0
    skipped_count = 0

    for record in iter_entityfacts_records(
        input_path=input_path,
        raw_limit=raw_limit,
    ):
        raw_count += 1

        normalized = normalize_entityfacts_record(
            record=record,
            only_type=only_type,
        )

        if normalized is None:
            skipped_count += 1
            continue

        normalized_count += 1

        if normalized_count % 10000 == 0:
            print(
                f"[ENTITYFACTS] raw={raw_count:,} "
                f"normalized={normalized_count:,} "
                f"skipped={skipped_count:,}",
                flush=True,
            )

        yield build_entityfacts_update_action(
            index_name=index_name,
            normalized=normalized,
        )

        if index_limit is not None and normalized_count >= index_limit:
            break

    print()
    print("[ENTITYFACTS] Finished")
    print(f"[ENTITYFACTS] Raw records seen:     {raw_count:,}")
    print(f"[ENTITYFACTS] Normalized/upserted:  {normalized_count:,}")
    print(f"[ENTITYFACTS] Skipped:              {skipped_count:,}")


def build_entityfacts_update_action(
    index_name: str,
    normalized: dict[str, Any],
) -> dict[str, Any]:
    """
    Builds an OpenSearch update action.

    Existing LDS records are enriched.
    Missing records are inserted via upsert.
    """
    gnd_id = normalized["id"]

    upsert_doc = dict(normalized)
    upsert_doc["source"] = "entityfacts"
    upsert_doc["sources"] = ["entityfacts"]

    return {
        "_op_type": "update",
        "_index": index_name,
        "_id": gnd_id,
        "scripted_upsert": True,
        "script": {
            "lang": "painless",
            "source": """
                if (ctx._source == null || ctx._source.isEmpty()) {
                    ctx._source.putAll(params.upsert_doc);
                    return;
                }

                if (!ctx._source.containsKey('sources') || ctx._source.sources == null) {
                    ctx._source.sources = new ArrayList();
                    if (ctx._source.containsKey('source') && ctx._source.source != null) {
                        ctx._source.sources.add(ctx._source.source);
                    }
                }

                if (!ctx._source.sources.contains('entityfacts')) {
                    ctx._source.sources.add('entityfacts');
                }

                for (entry in params.doc.entrySet()) {
                    String key = entry.getKey();
                    def value = entry.getValue();

                    if (key == 'id' || key == 'uri') {
                        if (!ctx._source.containsKey(key) || ctx._source[key] == null) {
                            ctx._source[key] = value;
                        }
                    } else if (key == 'preferredName') {
                        if (!ctx._source.containsKey(key) || ctx._source[key] == null || ctx._source[key] == '') {
                            ctx._source[key] = value;
                        }
                    } else if (key == 'type') {
                        if (!ctx._source.containsKey(key) || ctx._source[key] == null || ctx._source[key] == '') {
                            ctx._source[key] = value;
                        }
                    } else if (key == 'variantName') {
                        if (!ctx._source.containsKey('variantName') || ctx._source.variantName == null) {
                            ctx._source.variantName = new ArrayList();
                        }

                        if (!(ctx._source.variantName instanceof List)) {
                            def oldValue = ctx._source.variantName;
                            ctx._source.variantName = new ArrayList();
                            ctx._source.variantName.add(oldValue);
                        }

                        if (value instanceof List) {
                            for (item in value) {
                                if (!ctx._source.variantName.contains(item)) {
                                    ctx._source.variantName.add(item);
                                }
                            }
                        } else {
                            if (!ctx._source.variantName.contains(value)) {
                                ctx._source.variantName.add(value);
                            }
                        }
                    } else if (key == 'availableProperties') {
                        if (!ctx._source.containsKey('availableProperties') || ctx._source.availableProperties == null) {
                            ctx._source.availableProperties = new ArrayList();
                        }

                        for (item in value) {
                            if (!ctx._source.availableProperties.contains(item)) {
                                ctx._source.availableProperties.add(item);
                            }
                        }
                    } else if (key == 'propertiesFlat') {
                        if (!ctx._source.containsKey('propertiesFlat') || ctx._source.propertiesFlat == null) {
                            ctx._source.propertiesFlat = new ArrayList();
                        }

                        for (item in value) {
                            boolean exists = false;
                            for (existing in ctx._source.propertiesFlat) {
                                if (existing.id == item.id && existing.value == item.value) {
                                    exists = true;
                                    break;
                                }
                            }

                            if (!exists) {
                                ctx._source.propertiesFlat.add(item);
                            }
                        }
                    } else {
                        ctx._source[key] = value;
                    }
                }

                ctx._source.entityfactsEnriched = true;
            """,
            "params": {
                "doc": normalized,
                "upsert_doc": upsert_doc,
            },
        },
        "upsert": upsert_doc,
    }


def index_entityfacts(
    input_path: Path,
    index_name: str,
    only_type: str | None = None,
    index_limit: int | None = None,
    raw_limit: int | None = None,
    chunk_size: int = 1000,
) -> None:
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    client = get_opensearch_client()

    actions = generate_entityfacts_actions(
        input_path=input_path,
        index_name=index_name,
        only_type=only_type,
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

    print(f"[ENTITYFACTS] Successfully written: {success_count:,}")
    print(f"[ENTITYFACTS] Errors:               {error_count:,}")

    if error_count > 0:
        raise RuntimeError(f"EntityFacts indexing completed with {error_count} errors.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Index DNB GND EntityFacts records into OpenSearch via generic enrichment/upsert."
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Path to authorities-gnd_entityfacts.ndjson.gz",
    )

    parser.add_argument(
        "--index",
        default=INDEX_NAME,
        help="OpenSearch index name.",
    )

    parser.add_argument(
        "--only-type",
        default=None,
        help="Only index one normalized GND type, e.g. Family, CorporateBody, DifferentiatedPerson.",
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
        help="Maximum number of raw EntityFacts records to read.",
    )

    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1000,
        help="OpenSearch bulk chunk size.",
    )

    args = parser.parse_args()

    index_entityfacts(
        input_path=args.input,
        index_name=args.index,
        only_type=args.only_type,
        index_limit=args.limit,
        raw_limit=args.raw_limit,
        chunk_size=args.chunk_size,
    )


if __name__ == "__main__":
    main()
