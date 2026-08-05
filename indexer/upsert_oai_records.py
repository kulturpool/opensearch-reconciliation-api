import argparse
import json
import os
from pathlib import Path
from typing import Any

from opensearchpy import OpenSearch, helpers
from rdflib import Graph, RDF, URIRef


DEFAULT_INDEX = os.getenv("GND_INDEX_NAME", "gnd")
GND_URI_PREFIX = "https://d-nb.info/gnd/"
GND_NS = "https://d-nb.info/standards/elementset/gnd#"


PREFERRED_NAME_PREDICATES = [
    f"{GND_NS}preferredNameForThePerson",
    f"{GND_NS}preferredNameForTheFamily",
    f"{GND_NS}preferredNameForTheCorporateBody",
    f"{GND_NS}preferredNameForTheConferenceOrEvent",
    f"{GND_NS}preferredNameForThePlaceOrGeographicName",
    f"{GND_NS}preferredNameForTheSubjectHeading",
    f"{GND_NS}preferredNameForTheWork",
    f"{GND_NS}preferredName",
]

VARIANT_NAME_PREDICATES = [
    f"{GND_NS}variantNameForThePerson",
    f"{GND_NS}variantNameForTheFamily",
    f"{GND_NS}variantNameForTheCorporateBody",
    f"{GND_NS}variantNameForTheConferenceOrEvent",
    f"{GND_NS}variantNameForThePlaceOrGeographicName",
    f"{GND_NS}variantNameForTheSubjectHeading",
    f"{GND_NS}variantNameForTheWork",
    f"{GND_NS}variantName",
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
    "MusicalWork": "MusicalWork",
    "TerritorialCorporateBodyOrAdministrativeUnit": "TerritorialCorporateBodyOrAdministrativeUnit",
}


def get_opensearch_client() -> OpenSearch:
    host = os.getenv("OPENSEARCH_HOST", "opensearch")
    port = int(os.getenv("OPENSEARCH_PORT", "9200"))

    return OpenSearch(
        hosts=[{"host": host, "port": port}],
        http_compress=True,
        use_ssl=False,
        verify_certs=False,
        ssl_show_warn=False,
    )


def compact_uri(value: str) -> str:
    value = str(value)

    if "#" in value:
        return value.split("#")[-1]

    if "/" in value:
        return value.rstrip("/").split("/")[-1]

    return value


def deduplicate(values: list[str]) -> list:
    seen = set()
    result = []

    for value in values:
        if value in seen:
            continue

        seen.add(value)
        result.append(value)

    return result


def normalize_literal(value: Any) -> str:
    return str(value)


def parse_graph(metadata_xml: str) -> Graph:
    graph = Graph()
    graph.parse(data=metadata_xml, format="xml")
    return graph


def find_subject(graph: Graph, gnd_id: str) -> URIRef | None:
    expected_uri = URIRef(f"{GND_URI_PREFIX}{gnd_id}")

    if (expected_uri, None, None) in graph:
        return expected_uri

    for subject in graph.subjects():
        subject_str = str(subject)

        if subject_str.startswith(GND_URI_PREFIX):
            return subject

    return None


def get_first_value(
    graph: Graph,
    subject: URIRef,
    predicates: list[str],
) -> str | None:
    for predicate in predicates:
        for obj in graph.objects(subject, URIRef(predicate)):
            return normalize_literal(obj)

    return None


def get_all_values(
    graph: Graph,
    subject: URIRef,
    predicates: list[str],
) -> list:
    values = []

    for predicate in predicates:
        for obj in graph.objects(subject, URIRef(predicate)):
            values.append(normalize_literal(obj))

    return deduplicate(values)


def extract_type(graph: Graph, subject: URIRef) -> str | None:
    for obj in graph.objects(subject, RDF.type):
        type_id = compact_uri(str(obj))

        if type_id in TYPE_MAP:
            return TYPE_MAP[type_id]

    return None


def build_properties_flat(
    graph: Graph,
    subject: URIRef,
) -> tuple[list[str], list[dict[str, str]]]:
    available = []
    flat = []

    for predicate, obj in graph.predicate_objects(subject):
        prop_id = compact_uri(str(predicate))

        if prop_id == "type":
            continue

        value = normalize_literal(obj)

        if not value:
            continue

        available.append(prop_id)
        flat.append(
            {
                "id": prop_id,
                "value": value,
            }
        )

    return deduplicate(available), deduplicate_flat(flat)


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


def normalize_oai_record(item: dict[str, Any]) -> dict[str, Any] | None:
    gnd_id = item["id"]
    metadata_xml = item.get("metadata_xml")

    if not metadata_xml:
        return None

    graph = parse_graph(metadata_xml)
    subject = find_subject(graph, gnd_id)

    if subject is None:
        return None

    preferred_name = get_first_value(
        graph=graph,
        subject=subject,
        predicates=PREFERRED_NAME_PREDICATES,
    )

    if not preferred_name:
        return None

    variant_names = get_all_values(
        graph=graph,
        subject=subject,
        predicates=VARIANT_NAME_PREDICATES,
    )

    entity_type = extract_type(graph, subject)

    available_properties, properties_flat = build_properties_flat(
        graph=graph,
        subject=subject,
    )

    doc = {
        "id": gnd_id,
        "uri": f"{GND_URI_PREFIX}{gnd_id}",
        "preferredName": preferred_name,
        "variantName": variant_names,
        "availableProperties": available_properties,
        "propertiesFlat": properties_flat,
        "lastUpdateAction": "upsert",
        "oaiUpdated": True,
    }

    if entity_type:
        doc["type"] = entity_type

    return doc


def build_update_action(index_name: str, document: dict[str, Any]) -> dict[str, Any]:
    return {
        "_op_type": "update",
        "_index": index_name,
        "_id": document["id"],
        "doc": document,
        "doc_as_upsert": True,
    }


def iter_records(path: Path):
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue

            yield json.loads(line)


def upsert_records(
    records_file: Path,
    index_name: str,
    chunk_size: int = 500,
) -> None:
    client = get_opensearch_client()

    actions = []
    normalized_count = 0
    skipped_count = 0

    for item in iter_records(records_file):
        try:
            document = normalize_oai_record(item)

            if not document:
                skipped_count += 1
                continue

            actions.append(
                build_update_action(
                    index_name=index_name,
                    document=document,
                )
            )

            normalized_count += 1

        except Exception as error:
            skipped_count += 1
            print(
                f"[WARN] Failed to normalize OAI record {item.get('id')}: {error}",
                flush=True,
            )

        if len(actions) >= chunk_size:
            write_actions(client, actions, chunk_size)
            actions = []

    if actions:
        write_actions(client, actions, chunk_size)

    print(f"[OAI UPSERT] Normalized/upserted: {normalized_count:,}", flush=True)
    print(f"[OAI UPSERT] Skipped:             {skipped_count:,}", flush=True)

    if normalized_count == 0 and skipped_count > 0:
        raise RuntimeError(
            f"No OAI records were normalized. Skipped {skipped_count} records."
        )


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

    print(
        f"[OAI UPSERT] Bulk success: {success_count}, errors: {error_count}",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upsert OAI RDF/XML records directly into OpenSearch."
    )

    parser.add_argument(
        "--records-file",
        type=Path,
        required=True,
        help="JSONL file containing OAI records with metadata_xml.",
    )

    parser.add_argument(
        "--index",
        default=DEFAULT_INDEX,
        help="OpenSearch index name.",
    )

    parser.add_argument(
        "--chunk-size",
        type=int,
        default=500,
        help="OpenSearch bulk chunk size.",
    )

    args = parser.parse_args()

    upsert_records(
        records_file=args.records_file,
        index_name=args.index,
        chunk_size=args.chunk_size,
    )


if __name__ == "__main__":
    main()