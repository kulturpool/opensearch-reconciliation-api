import html
from typing import Any

GND_NS = "https://d-nb.info/standards/elementset/gnd#"
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"

FIELD_GND_IDENTIFIER = f"{GND_NS}gndIdentifier"

RDF_SEQ = f"{RDF_NS}Seq"
RDF_ITEM_PREFIX = RDF_NS + "_"

PREFERRED_NAME_FIELDS = [
    f"{GND_NS}preferredNameForThePerson",
    f"{GND_NS}preferredNameForTheCorporateBody",
    f"{GND_NS}preferredNameForTheConferenceOrEvent",
    f"{GND_NS}preferredNameForThePlaceOrGeographicName",
    f"{GND_NS}preferredNameForTheSubjectHeading",
    f"{GND_NS}preferredNameForTheWork",
    f"{GND_NS}preferredName",
]

VARIANT_NAME_FIELDS = [
    f"{GND_NS}variantNameForThePerson",
    f"{GND_NS}variantNameForTheCorporateBody",
    f"{GND_NS}variantNameForTheConferenceOrEvent",
    f"{GND_NS}variantNameForThePlaceOrGeographicName",
    f"{GND_NS}variantNameForTheSubjectHeading",
    f"{GND_NS}variantNameForTheWork",
    f"{GND_NS}variantName",
]

DATE_OF_BIRTH_FIELDS = [
    f"{GND_NS}dateOfBirth",
    f"{GND_NS}dateOfBirthAndDeath",
]

DATE_OF_DEATH_FIELDS = [
    f"{GND_NS}dateOfDeath",
]

PROFESSION_FIELDS = [
    f"{GND_NS}professionOrOccupation",
]

PLACE_OF_BIRTH_FIELDS = [
    f"{GND_NS}placeOfBirth",
]

PLACE_OF_DEATH_FIELDS = [
    f"{GND_NS}placeOfDeath",
]

LABEL_FIELDS = [
    f"{GND_NS}preferredNameForThePerson",
    f"{GND_NS}preferredNameForTheCorporateBody",
    f"{GND_NS}preferredNameForTheConferenceOrEvent",
    f"{GND_NS}preferredNameForThePlaceOrGeographicName",
    f"{GND_NS}preferredNameForTheSubjectHeading",
    f"{GND_NS}preferredNameForTheWork",
    f"{GND_NS}preferredName",
    f"{GND_NS}variantNameForThePerson",
    f"{GND_NS}variantNameForTheSubjectHeading",
    "http://www.w3.org/2004/02/skos/core#prefLabel",
    "http://www.w3.org/2000/01/rdf-schema#label",
]


def normalize_gnd_lds_record(
    record: dict[str, Any],
    source_key: str | None = None,
    node_map: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """
    Normalizes one DNB GND LDS JSON-LD record into our local OpenSearch schema.

    Returns None for:
    - blank nodes
    - /about metadata records
    - records without GND identifier
    - records without preferred name
    """

    uri = record.get("@id")

    if not is_indexable_gnd_uri(uri):
        return None

    gnd_id = extract_gnd_id(record)

    if not gnd_id:
        return None

    preferred_name = extract_first_value_from_fields(
        record=record,
        fields=PREFERRED_NAME_FIELDS,
        node_map=node_map,
    )

    if not preferred_name:
        return None

    variant_names = extract_values_from_fields(
        record=record,
        fields=VARIANT_NAME_FIELDS,
        node_map=node_map,
    )

    entity_types = extract_types(record)

    available_properties, properties_flat = extract_all_gnd_properties(
        record=record,
        node_map=node_map,
    )

    normalized = {
        "id": gnd_id,
        "uri": uri,
        "preferredName": preferred_name,
        "variantName": variant_names,
        "type": entity_types,
        "dateOfBirth": extract_first_value_from_fields(
            record=record,
            fields=DATE_OF_BIRTH_FIELDS,
            node_map=node_map,
        ),
        "dateOfDeath": extract_first_value_from_fields(
            record=record,
            fields=DATE_OF_DEATH_FIELDS,
            node_map=node_map,
        ),
        "professionOrOccupation": extract_values_from_fields(
            record=record,
            fields=PROFESSION_FIELDS,
            node_map=node_map,
        ),
        "placeOfBirth": extract_values_from_fields(
            record=record,
            fields=PLACE_OF_BIRTH_FIELDS,
            node_map=node_map,
        ),
        "placeOfDeath": extract_values_from_fields(
            record=record,
            fields=PLACE_OF_DEATH_FIELDS,
            node_map=node_map,
        ),
        "source": "dnb-gnd-lds",
        "availableProperties": available_properties,
        "propertiesFlat": properties_flat,
    }

    return normalized


def is_indexable_gnd_uri(uri: Any) -> bool:
    """
    Checks whether the @id points to a real GND entity.

    We skip:
    - blank nodes: _:node...
    - metadata records: .../about
    """

    if not isinstance(uri, str):
        return False

    if not uri.startswith("https://d-nb.info/gnd/"):
        return False

    if uri.endswith("/about"):
        return False

    return True


def extract_gnd_id(record: dict[str, Any]) -> str | None:
    """
    Extracts GND identifier from the explicit gndIdentifier field,
    falling back to the URI suffix.
    """

    value = extract_first_value(record.get(FIELD_GND_IDENTIFIER))

    if value:
        return value

    uri = record.get("@id")

    if isinstance(uri, str) and uri.startswith("https://d-nb.info/gnd/"):
        return uri.rstrip("/").split("/")[-1]

    return None


def extract_types(record: dict[str, Any]) -> list[str]:
    """
    Extracts compact type names from @type URIs.

    Example:
    https://d-nb.info/standards/elementset/gnd#SubjectHeadingSensoStricto
    becomes:
    SubjectHeadingSensoStricto
    """

    raw_types = record.get("@type", [])

    if isinstance(raw_types, str):
        raw_types = [raw_types]

    if not isinstance(raw_types, list):
        return []

    result = []

    for raw_type in raw_types:
        if not isinstance(raw_type, str):
            continue

        if "#" in raw_type:
            result.append(raw_type.split("#")[-1])
        else:
            result.append(raw_type.rstrip("/").split("/")[-1])

    return result


def extract_first_value_from_fields(
    record: dict[str, Any],
    fields: list[str],
    node_map: dict[str, dict[str, Any]] | None = None,
) -> str | None:
    values = extract_values_from_fields(
        record=record,
        fields=fields,
        node_map=node_map,
    )

    if not values:
        return None

    return values[0]


def extract_values_from_fields(
    record: dict[str, Any],
    fields: list[str],
    node_map: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    values: list[str] = []

    for field in fields:
        values.extend(
            extract_values(
                record.get(field),
                node_map=node_map,
            )
        )

    return deduplicate_preserving_order(values)


def extract_first_value(
    value: Any,
    node_map: dict[str, dict[str, Any]] | None = None,
) -> str | None:
    values = extract_values(
        value,
        node_map=node_map,
    )

    if not values:
        return None

    return values[0]


def extract_values(
    value: Any,
    node_map: dict[str, dict[str, Any]] | None = None,
    visited: set[str] | None = None,
) -> list:
    """
    Extracts readable values from JSON-LD values.

    Supports:
    - {"@value": "..."}
    - {"@id": "https://..."}
    - {"@id": "_:node..."} with node resolution
    - rdf:Seq containers with rdf:_1, rdf:_2, ...
    """

    if visited is None:
        visited = set()

    if value is None:
        return []

    if isinstance(value, str):
        return [html.unescape(value)]

    if isinstance(value, (int, float)):
        return [str(value)]

    if isinstance(value, list):
        values: list[str] = []

        for item in value:
            values.extend(
                extract_values(
                    item,
                    node_map=node_map,
                    visited=visited,
                )
            )

        return values

    if isinstance(value, dict):
        if "@value" in value:
            return [html.unescape(str(value["@value"]))]

        if "@id" in value:
            ref_id = str(value["@id"])

            if ref_id in visited:
                return []

            if node_map and ref_id in node_map:
                visited.add(ref_id)

                resolved_record = node_map[ref_id]

                return extract_label_or_sequence_values(
                    resolved_record,
                    node_map=node_map,
                    visited=visited,
                )

            return [ref_id]

    return []


def deduplicate_preserving_order(values: list[str]) -> list[str]:
    """
    Removes duplicates while preserving order.
    """

    seen = set()
    result = []

    for value in values:
        if not value:
            continue

        value = html.unescape(value)

        if value in seen:
            continue

        seen.add(value)
        result.append(value)

    return result


def extract_label_or_sequence_values(
    record: dict[str, Any],
    node_map: dict[str, dict[str, Any]] | None = None,
    visited: set[str] | None = None,
) -> list[str]:
    """
    Resolves either:
    - a labeled record
    - an rdf:Seq container
    """

    if is_rdf_sequence(record):
        return extract_rdf_sequence_values(
            record=record,
            node_map=node_map,
            visited=visited,
        )

    label = extract_label_from_record(
        record=record,
        node_map=node_map,
        visited=visited,
    )

    if label:
        return [label]

    uri = record.get("@id")

    if isinstance(uri, str):
        return [uri]

    return []


def is_rdf_sequence(record: dict[str, Any]) -> bool:
    raw_types = record.get("@type", [])

    if isinstance(raw_types, str):
        raw_types = [raw_types]

    return RDF_SEQ in raw_types


def extract_rdf_sequence_values(
    record: dict[str, Any],
    node_map: dict[str, dict[str, Any]] | None = None,
    visited: set[str] | None = None,
) -> list[str]:
    """
    Extracts ordered values from rdf:_1, rdf:_2, ...
    """

    sequence_keys = []

    for key in record.keys():
        if not key.startswith(RDF_ITEM_PREFIX):
            continue

        suffix = key.replace(RDF_ITEM_PREFIX, "")

        if suffix.isdigit():
            sequence_keys.append((int(suffix), key))

    sequence_keys.sort(key=lambda item: item[0])

    values: list[str] = []

    for _, key in sequence_keys:
        values.extend(
            extract_values(
                record.get(key),
                node_map=node_map,
                visited=visited,
            )
        )

    return values


def extract_label_from_record(
    record: dict[str, Any],
    node_map: dict[str, dict[str, Any]] | None = None,
    visited: set[str] | None = None,
) -> str | None:
    for field in LABEL_FIELDS:
        values = extract_values(
            record.get(field),
            node_map=node_map,
            visited=visited,
        )

        if values:
            return values[0]

    return None


def compact_gnd_property_id(uri: str) -> str | None:
    """
    Converts a full GND property URI to a compact property id.

    Example:
    https://d-nb.info/standards/elementset/gnd#academicDegree
    -> academicDegree
    """

    if not isinstance(uri, str):
        return None

    if not uri.startswith(GND_NS):
        return None

    return uri.split("#")[-1]


def extract_all_gnd_properties(
    record: dict[str, Any],
    node_map: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[str], list[dict[str, str]]]:
    """
    Extracts all GND namespace properties from one JSON-LD record.

    Returns:
    - availableProperties: list of property ids
    - propertiesFlat: list of {"id": ..., "value": ...}
    """

    available_properties: list[str] = []
    properties_flat: list[dict[str, str]] = []

    for raw_key, raw_value in record.items():
        property_id = compact_gnd_property_id(raw_key)

        if not property_id:
            continue

        values = extract_values(
            raw_value,
            node_map=node_map,
        )

        if not values:
            continue

        available_properties.append(property_id)

        for value in values:
            properties_flat.append(
                {
                    "id": property_id,
                    "value": value,
                }
            )

    return (
        deduplicate_preserving_order(available_properties),
        properties_flat,
    )
