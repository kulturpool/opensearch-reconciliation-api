import argparse
import json
from pathlib import Path
from typing import Any

from opensearchpy import OpenSearch, helpers

DEFAULT_INDEX_NAME = "gnd"
DEFAULT_INPUT_FILE = "data/raw/sample_gnd.json"


def get_opensearch_client() -> OpenSearch:
    """
    Creates an OpenSearch client for the local devcontainer setup.

    Inside the DevContainer, the OpenSearch service is reachable via:
    http://opensearch:9200
    """

    return OpenSearch(
        hosts=[{"host": "opensearch", "port": 9200}],
        http_compress=True,
        use_ssl=False,
        verify_certs=False,
        ssl_show_warn=False,
    )


# TODO: Check if this mapping is correct or if we can improve it
def create_index(client: OpenSearch, index_name: str, recreate: bool = False) -> None:
    """
    Creates the GND index with a basic mapping.

    If recreate=True, an existing index will be deleted and recreated.
    """

    if client.indices.exists(index=index_name):
        if recreate:
            print(f"Deleting existing index: {index_name}")
            client.indices.delete(index=index_name)
        else:
            print(f"Index already exists: {index_name}")
            return

    mapping = {
        "settings": {
            "index": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
            },
            "analysis": {
                "analyzer": {
                    "gnd_text_analyzer": {
                        "type": "standard",
                        "stopwords": "_none_",
                    }
                }
            },
        },
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "uri": {"type": "keyword"},
                "preferredName": {
                    "type": "text",
                    "analyzer": "gnd_text_analyzer",
                    "fields": {"keyword": {"type": "keyword"}},
                },
                "variantName": {"type": "text", "analyzer": "gnd_text_analyzer"},
                "type": {"type": "keyword"},
                "dateOfBirth": {"type": "keyword"},
                "dateOfDeath": {"type": "keyword"},
                "professionOrOccupation": {
                    "type": "text",
                    "analyzer": "gnd_text_analyzer",
                },
                "placeOfBirth": {"type": "text", "analyzer": "gnd_text_analyzer"},
                "placeOfDeath": {"type": "text", "analyzer": "gnd_text_analyzer"},
                "source": {"type": "keyword"},
            }
        },
    }

    print(f"Creating index: {index_name}")
    client.indices.create(index=index_name, body=mapping)


def load_records(input_file: str) -> list[dict[str, Any]]:
    """
    Loads a small JSON test dataset.

    Expected format:
    [
      {
        "id": "...",
        "preferredName": "...",
        "variantName": [...]
      }
    ]
    """

    path = Path(input_file)

    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    with path.open("r", encoding="utf-8") as file:
        records = json.load(file)

    if not isinstance(records, list):
        raise TypeError("Input file must contain a JSON array of records.")

    return records


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    """
    Normalizes one GND-like record before indexing.

    This makes sure every document has a stable structure.
    """

    gnd_id = record.get("id")

    if not gnd_id:
        raise ValueError(f"Record is missing required field 'id': {record}")

    preferred_name = record.get("preferredName") or record.get("name")

    if not preferred_name:
        raise ValueError(f"Record is missing required field 'preferredName': {record}")

    variant_names = record.get("variantName", [])

    if isinstance(variant_names, str):
        variant_names = [variant_names]

    entity_type = record.get("type", "Unknown")

    if isinstance(entity_type, list):
        types = entity_type
    else:
        types = [entity_type]

    normalized = {
        "id": gnd_id,
        "uri": record.get("uri", f"https://d-nb.info/gnd/{gnd_id}"),
        "preferredName": preferred_name,
        "variantName": variant_names,
        "type": types,
        "dateOfBirth": record.get("dateOfBirth"),
        "dateOfDeath": record.get("dateOfDeath"),
        "professionOrOccupation": record.get("professionOrOccupation", []),
        "placeOfBirth": record.get("placeOfBirth"),
        "placeOfDeath": record.get("placeOfDeath"),
        "source": record.get("source", "sample"),
    }

    return normalized


def generate_bulk_actions(
    records: list[dict[str, Any]],
    index_name: str,
):
    """
    Generates bulk indexing actions for OpenSearch.
    """

    for record in records:
        normalized = normalize_record(record)

        yield {
            "_index": index_name,
            "_id": normalized["id"],
            "_source": normalized,
        }


def index_records(
    client: OpenSearch,
    records: list[dict[str, Any]],
    index_name: str,
) -> None:
    """
    Bulk indexes records into OpenSearch.
    """

    actions = generate_bulk_actions(records, index_name)

    success_count, errors = helpers.bulk(
        client,
        actions,
        stats_only=False,
        raise_on_error=False,
    )

    client.indices.refresh(index=index_name)

    print(f"Indexed records: {success_count}")

    if errors:
        print("Some records failed to index:")
        for error in errors:
            print(error)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Index a small local GND test dataset into OpenSearch."
    )

    parser.add_argument(
        "--input",
        default=DEFAULT_INPUT_FILE,
        help=f"Path to input JSON file. Default: {DEFAULT_INPUT_FILE}",
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

    args = parser.parse_args()

    client = get_opensearch_client()

    print("Checking OpenSearch connection...")
    info = client.info()
    print(f"Connected to OpenSearch: {info.get('version', {}).get('number')}")

    records = load_records(args.input)
    print(f"Loaded records: {len(records)}")

    create_index(
        client=client,
        index_name=args.index,
        recreate=args.recreate,
    )

    index_records(
        client=client,
        records=records,
        index_name=args.index,
    )

    print("Done.")


if __name__ == "__main__":
    main()
