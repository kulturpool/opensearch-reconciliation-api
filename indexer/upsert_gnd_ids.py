import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

# Add parent directory to path to allow imports from config
sys.path.insert(0, str(Path(__file__).parent.parent))

from opensearchpy import OpenSearch, helpers

from config import (
    GND_RECORD_JSONLD_URL_TEMPLATE,
    GND_UPSERT_FAILED_IDS_FILE,
    GND_UPSERT_REQUEST_BACKOFF_SECONDS,
    GND_UPSERT_REQUEST_DELAY_SECONDS,
    GND_UPSERT_REQUEST_MAX_RETRIES,
    INDEX_NAME,
    OPENSEARCH_HOST,
    OPENSEARCH_PORT,
)

GND_URI_PREFIX = "https://d-nb.info/gnd/"
GND_NS = "https://d-nb.info/standards/elementset/gnd#"


PREFERRED_NAME_FIELDS = [
    f"{GND_NS}preferredNameForThePerson",
    f"{GND_NS}preferredNameForTheFamily",
    f"{GND_NS}preferredNameForTheCorporateBody",
    f"{GND_NS}preferredNameForTheConferenceOrEvent",
    f"{GND_NS}preferredNameForThePlaceOrGeographicName",
    f"{GND_NS}preferredNameForTheSubjectHeading",
    f"{GND_NS}preferredNameForTheWork",
    f"{GND_NS}preferredName",
    "preferredName",
    "http://www.w3.org/2004/02/skos/core#prefLabel",
]

VARIANT_NAME_FIELDS = [
    f"{GND_NS}variantNameForThePerson",
    f"{GND_NS}variantNameForTheFamily",
    f"{GND_NS}variantNameForTheCorporateBody",
    f"{GND_NS}variantNameForTheConferenceOrEvent",
    f"{GND_NS}variantNameForThePlaceOrGeographicName",
    f"{GND_NS}variantNameForTheSubjectHeading",
    f"{GND_NS}variantNameForTheWork",
    f"{GND_NS}variantName",
    "variantName",
    "http://www.w3.org/2004/02/skos/core#altLabel",
]

TYPE_MAP = {
    "DifferentiatedPerson": "DifferentiatedPerson",
    "UndifferentiatedPerson": "UndifferentiatedPerson",
    "Family": "Family",
    "CorporateBody": "CorporateBody",
    "ConferenceOrEvent": "ConferenceOrEvent",
    "PlaceOrGeographicName": "PlaceOrGeographicName",
    "SubjectHeading": "SubjectHeading",
    "SubjectHeadingSensoStricto": "SubjectHeadingSensoStricto",
    "Work": "Work",
}


def get_opensearch_client() -> OpenSearch:
    return OpenSearch(
        hosts=[{"host": OPENSEARCH_HOST, "port": OPENSEARCH_PORT}],
        http_compress=True,
        use_ssl=False,
        verify_certs=False,
        ssl_show_warn=False,
    )


def fetch_json(url: str, timeout: int = 120) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "local-gnd-reconciliation-api/0.1",
            "Accept": "application/ld+json, application/json",
        },
    )

    last_error = None

    for attempt in range(1, GND_UPSERT_REQUEST_MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))

        except urllib.error.HTTPError as error:
            last_error = error

            if error.code == 404:
                raise

            wait_seconds = GND_UPSERT_REQUEST_BACKOFF_SECONDS * attempt

            print(
                f"[WARN] HTTP error for {url}: {error}. "
                f"Retry {attempt}/{GND_UPSERT_REQUEST_MAX_RETRIES} in {wait_seconds}s",
                flush=True,
            )

            time.sleep(wait_seconds)

        except urllib.error.URLError as error:
            last_error = error
            wait_seconds = GND_UPSERT_REQUEST_BACKOFF_SECONDS * attempt

            print(
                f"[WARN] URL error for {url}: {error}. "
                f"Retry {attempt}/{GND_UPSERT_REQUEST_MAX_RETRIES} in {wait_seconds}s",
                flush=True,
            )

            time.sleep(wait_seconds)

    raise RuntimeError(f"Failed to fetch {url} after retries: {last_error}")


def fetch_gnd_jsonld(gnd_id: str) -> Any:
    url = GND_RECORD_JSONLD_URL_TEMPLATE.format(id=urllib.parse.quote(gnd_id))
    return fetch_json(url)


def as_list(value: Any) -> list:
    if value is None:
        return []

    if isinstance(value, list):
        return value

    return [value]


def compact_uri(value: str) -> str:
    value = str(value)

    if "#" in value:
        return value.split("#")[-1]

    if "/" in value:
        return value.rstrip("/").split("/")[-1]

    return value


def extract_id_from_uri(value: str) -> str | None:
    value = str(value)

    if value.startswith(GND_URI_PREFIX):
        return value.replace(GND_URI_PREFIX, "").strip("/")

    return None


def find_record(data: Any, expected_id: str) -> dict[str, Any] | None:
    """
    Finds the GND record object in returned JSON-LD.
    """

    records = []

    if isinstance(data, dict) and "@graph" in data:
        records = data["@graph"]
    elif isinstance(data, list):
        records = data
    elif isinstance(data, dict):
        records = [data]

    for record in records:
        if not isinstance(record, dict):
            continue

        raw_id = record.get("@id") or record.get("id")

        if not raw_id:
            continue

        gnd_id = extract_id_from_uri(str(raw_id))

        if gnd_id == expected_id:
            return record

    # fallback: first GND-like record
    for record in records:
        if not isinstance(record, dict):
            continue

        raw_id = record.get("@id") or record.get("id")

        if raw_id and str(raw_id).startswith(GND_URI_PREFIX):
            return record

    return None


def extract_values(value: Any) -> list:
    if value is None:
        return []

    if isinstance(value, str):
        return [value]

    if isinstance(value, (int, float)):
        return [str(value)]

    if isinstance(value, list):
        result = []

        for item in value:
            result.extend(extract_values(item))

        return deduplicate(result)

    if isinstance(value, dict):
        result = []

        raw_id = value.get("@id") or value.get("id")

        if raw_id:
            result.append(str(raw_id))

        label = (
            value.get("preferredName")
            or value.get("label")
            or value.get("name")
            or value.get("@value")
            or value.get("value")
        )

        if label:
            result.append(str(label))

        return deduplicate(result)

    return [str(value)]


def first_value(record: dict[str, Any], fields: list[str]) -> str | None:
    for field in fields:
        if field not in record:
            continue

        values = extract_values(record[field])

        if values:
            return values[0]

    return None


def all_values(record: dict[str, Any], fields: list[str]) -> list:
    result = []

    for field in fields:
        if field not in record:
            continue

        result.extend(extract_values(record[field]))

    return deduplicate(result)


def extract_type(record: dict[str, Any]) -> str | None:
    raw_types = record.get("@type") or record.get("type") or []

    for raw_type in as_list(raw_types):
        type_id = compact_uri(str(raw_type))

        if type_id in TYPE_MAP:
            return TYPE_MAP[type_id]

    return None


def compact_property_id(prop_id: str) -> str:
    prop_id = str(prop_id)

    if prop_id.startswith(GND_NS):
        return prop_id.replace(GND_NS, "")

    if "#" in prop_id:
        return prop_id.split("#")[-1]

    if "/" in prop_id:
        return prop_id.rstrip("/").split("/")[-1]

    return prop_id


def build_properties_flat(
    record: dict[str, Any],
) -> tuple[list[str], list[dict[str, str]]]:
    available = []
    flat = []

    skip_keys = {
        "@context",
        "@id",
        "@type",
        "id",
        "type",
    }

    for raw_key, raw_value in record.items():
        if raw_key in skip_keys:
            continue

        prop_id = compact_property_id(raw_key)
        values = extract_values(raw_value)

        if not values:
            continue

        available.append(prop_id)

        for value in values:
            flat.append(
                {
                    "id": prop_id,
                    "value": value,
                }
            )

    return deduplicate(available), deduplicate_flat(flat)


def normalize_gnd_jsonld_record(
    data: Any,
    gnd_id: str,
) -> dict[str, Any] | None:
    record = find_record(data, gnd_id)

    if not record:
        return None

    preferred_name = first_value(record, PREFERRED_NAME_FIELDS)

    if not preferred_name:
        return None

    variant_names = all_values(record, VARIANT_NAME_FIELDS)
    gnd_type = extract_type(record)

    available_properties, properties_flat = build_properties_flat(record)

    normalized: dict[str, Any] = {
        "id": gnd_id,
        "uri": f"{GND_URI_PREFIX}{gnd_id}",
        "preferredName": preferred_name,
        "variantName": variant_names,
        "availableProperties": available_properties,
        "propertiesFlat": properties_flat,
        "lastUpdateAction": "upsert",
    }

    if gnd_type:
        normalized["type"] = gnd_type

    return normalized


def build_update_action(
    index_name: str,
    document: dict[str, Any],
) -> dict[str, Any]:
    gnd_id = document["id"]

    return {
        "_op_type": "update",
        "_index": index_name,
        "_id": gnd_id,
        "doc": document,
        "doc_as_upsert": True,
    }


def deduplicate(values: list[str]) -> list:
    seen = set()
    result = []

    for value in values:
        if value in seen:
            continue

        seen.add(value)
        result.append(value)

    return result


def deduplicate_flat(values: list[dict[str, str]]) -> list[dict[str, str]]:
    seen = set()
    result = []

    for item in values:
        key = (
            item.get("id"),
            item.get("value"),
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(item)

    return result


def read_ids_file(path: Path) -> list:
    ids = []

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue

            item = json.loads(line)
            gnd_id = item.get("id")

            if gnd_id:
                ids.append(str(gnd_id))

    return deduplicate(ids)


def upsert_ids(
    ids: list[str],
    index_name: str,
    chunk_size: int = 500,
) -> None:
    client = get_opensearch_client()

    actions = []
    fetched = 0
    skipped = 0

    for gnd_id in ids:
        try:
            data = fetch_gnd_jsonld(gnd_id)
            document = normalize_gnd_jsonld_record(data, gnd_id)

            if not document:
                skipped += 1
                continue

            actions.append(
                build_update_action(
                    index_name=index_name,
                    document=document,
                )
            )

            fetched += 1

        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, KeyError, ValueError, OSError) as error:
            skipped += 1
            write_failed_id(gnd_id, error)
            print(f"[WARN] Failed to fetch/upsert {gnd_id}: {error}", flush=True)

        finally:
            if GND_UPSERT_REQUEST_DELAY_SECONDS > 0:
                time.sleep(GND_UPSERT_REQUEST_DELAY_SECONDS)

        if len(actions) >= chunk_size:
            write_actions(client, actions, chunk_size)
            actions = []

    if actions:
        write_actions(client, actions, chunk_size)

    print(f"[UPSERT] Fetched/upserted: {fetched:,}", flush=True)
    print(f"[UPSERT] Skipped:          {skipped:,}", flush=True)


def write_actions(
    client: OpenSearch,
    actions: list[dict[str, Any]],
    chunk_size: int,
) -> None:
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

    print(f"[UPSERT] Bulk success: {success_count}, errors: {error_count}", flush=True)


def write_failed_id(gnd_id: str, error: Exception) -> None:
    GND_UPSERT_FAILED_IDS_FILE.parent.mkdir(parents=True, exist_ok=True)

    with GND_UPSERT_FAILED_IDS_FILE.open("a", encoding="utf-8") as file:
        file.write(
            json.dumps(
                {
                    "id": gnd_id,
                    "error": str(error),
                },
                ensure_ascii=False,
            )
            + "\n"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch and upsert changed GND records by ID."
    )

    parser.add_argument(
        "--ids-file",
        type=Path,
        required=True,
        help="JSONL file with changed GND IDs.",
    )

    parser.add_argument(
        "--index",
        default=INDEX_NAME,
        help="OpenSearch index name.",
    )

    parser.add_argument(
        "--chunk-size",
        type=int,
        default=500,
        help="Bulk chunk size.",
    )

    args = parser.parse_args()

    ids = read_ids_file(args.ids_file)

    print(f"[UPSERT] IDs to process: {len(ids):,}", flush=True)

    upsert_ids(
        ids=ids,
        index_name=args.index,
        chunk_size=args.chunk_size,
    )


if __name__ == "__main__":
    main()
