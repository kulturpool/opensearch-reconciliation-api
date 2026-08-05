from typing import Any
from urllib.parse import unquote


GND_URI_PREFIX = "https://d-nb.info/gnd/"


ENTITYFACTS_TYPE_TO_GND_TYPE = {
    "person": "DifferentiatedPerson",
    "organisation": "CorporateBody",
    "organization": "CorporateBody",
    "event": "ConferenceOrEvent",
    "place": "PlaceOrGeographicName",
    "family": "Family",
}


COMMON_ENTITYFACTS_TOP_LEVEL_FIELDS = [
    "surname",
    "forename",
    "dateOfBirth",
    "dateOfDeath",
    "dateOfBirthAndDeath",
    "periodOfActivity",
    "biographicalOrHistoricalInformation",
    "gender",
    "associatedCountry",
    "professionOrOccupation",
    "placeOfBirth",
    "placeOfDeath",
    "placeOfActivity",
    "affiliation",
    "academicDegree",
    "familialRelationship",
    "relatedPerson",
    "sameAs",
    "depiction",
    "homepage",
    "location",
    "dateOfEstablishment",
    "dateOfTermination",
    "dateOfEvent",
    "placeOfEvent",
    "placeOfBusiness",
    "isPartOf",
    "isA",
    "successor",
    "predecessor",
    "topic",
    "relatedOrganisation",
    "relatedEvent",
    "associatedPlace",
]


def normalize_entityfacts_record(
    record: dict[str, Any],
    only_type: str | None = None,
) -> dict[str, Any] | None:
    """
    Normalizes one EntityFacts NDJSON record into our OpenSearch document format.

    EntityFacts is used as an enrichment layer:
    - existing LDS records can be enriched
    - missing records, especially Family, can be inserted
    """

    gnd_id = extract_gnd_id(record)

    if not gnd_id:
        return None

    entityfacts_type = extract_entityfacts_type(record)

    if not entityfacts_type:
        return None

    gnd_type = ENTITYFACTS_TYPE_TO_GND_TYPE.get(entityfacts_type)

    if not gnd_type:
        return None

    if only_type and gnd_type != only_type:
        return None

    preferred_name = extract_preferred_name(record)

    if not preferred_name:
        return None

    variant_names = extract_variant_names(record)

    available_properties, properties_flat = extract_entityfacts_properties(record)

    normalized: dict[str, Any] = {
        "id": gnd_id,
        "uri": f"{GND_URI_PREFIX}{gnd_id}",
        "preferredName": preferred_name,
        "variantName": variant_names,
        "type": gnd_type,
        "entityfactsType": entityfacts_type,
        "entityfactsEnriched": True,
        "availableProperties": available_properties,
        "propertiesFlat": properties_flat,
    }

    for prop_id in COMMON_ENTITYFACTS_TOP_LEVEL_FIELDS:
        values = get_values_for_property(
            properties_flat=properties_flat,
            prop_id=prop_id,
        )

        if values:
            normalized[prop_id] = values if len(values) > 1 else values[0]

    return normalized


def extract_gnd_id(record: dict[str, Any]) -> str | None:
    raw_id = record.get("@id") or record.get("id")

    if not raw_id:
        return None

    raw_id = unquote(str(raw_id)).strip()

    if raw_id.startswith(GND_URI_PREFIX):
        return raw_id.replace(GND_URI_PREFIX, "").strip("/")

    return raw_id


def extract_entityfacts_type(record: dict[str, Any]) -> str | None:
    raw_type = record.get("@type") or record.get("type")

    if isinstance(raw_type, list):
        if not raw_type:
            return None

        raw_type = raw_type[0]

    if not raw_type:
        return None

    return str(raw_type).strip().lower()


def extract_preferred_name(record: dict[str, Any]) -> str | None:
    value = (
        record.get("preferredName")
        or record.get("surname")
        or record.get("label")
        or record.get("name")
    )

    if not value:
        return None

    return str(value)


def extract_variant_names(record: dict[str, Any]) -> list:
    value = record.get("variantName")

    if value is None:
        return []

    if isinstance(value, list):
        return deduplicate_preserving_order(
            [
                str(item)
                for item in value
                if item is not None
            ]
        )

    return [str(value)]


def extract_entityfacts_properties(
    record: dict[str, Any],
) -> tuple[list[str], list[dict[str, str]]]:
    """
    Extracts EntityFacts fields into:
    - availableProperties
    - propertiesFlat
    """

    available_properties: list[str] = []
    properties_flat: list[dict[str, str]] = []

    skip_keys = {
        "@context",
        "@id",
        "@type",
        "describedBy",
    }

    for prop_id, raw_value in record.items():
        if prop_id in skip_keys:
            continue

        values = extract_values(raw_value)

        if not values:
            continue

        available_properties.append(prop_id)

        for value in values:
            properties_flat.append(
                {
                    "id": prop_id,
                    "value": value,
                }
            )

    return (
        deduplicate_preserving_order(available_properties),
        deduplicate_properties_flat(properties_flat),
    )


def extract_values(value: Any) -> list:
    """
    Extracts readable/indexable string values from EntityFacts structures.

    Handles:
    - strings
    - numbers
    - lists
    - dicts with @id, id, preferredName, label, name
    """

    if value is None:
        return []

    if isinstance(value, str):
        return [value]

    if isinstance(value, (int, float)):
        return [str(value)]

    if isinstance(value, list):
        values: list[str] = []

        for item in value:
            values.extend(extract_values(item))

        return deduplicate_preserving_order(values)

    if isinstance(value, dict):
        values: list[str] = []

        raw_id = value.get("@id") or value.get("id")

        if raw_id:
            values.append(str(raw_id))

        label = (
            value.get("preferredName")
            or value.get("label")
            or value.get("name")
        )

        if label:
            values.append(str(label))

        relationship = value.get("relationship")

        if relationship:
            values.append(str(relationship))

        return deduplicate_preserving_order(values)

    return [str(value)]


def get_values_for_property(
    properties_flat: list[dict[str, str]],
    prop_id: str,
) -> list:
    values = []

    for item in properties_flat:
        if item.get("id") == prop_id and item.get("value"):
            values.append(item["value"])

    return deduplicate_preserving_order(values)


def deduplicate_preserving_order(values: list[str]) -> list:
    seen = set()
    result = []

    for value in values:
        if value in seen:
            continue

        seen.add(value)
        result.append(value)

    return result


def deduplicate_properties_flat(
    values: list[dict[str, str]],
) -> list[dict[str, str]]:
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