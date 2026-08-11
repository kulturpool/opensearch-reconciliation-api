import re
from typing import Any

from opensearchpy import OpenSearchException

from api.services.property_labels import property_label
from api.services.search import (
    GND_TYPE_ALIASES,
    INDEX_NAME,
    client,
    format_entity_types,
    get_gnd_record_by_id,
)
from api.services.vocab_resolver import resolve_gnd_vocab_uri

GND_URI_RE = re.compile(r"https?://d-nb\.info/gnd/([^/#?\s\"<>]+)")
GND_ID_RE = re.compile(r"^[0-9Xx][0-9Xx-]*$")
GND_URI_PREFIX = "https://d-nb.info/gnd/"


RELATION_PROPERTY_TYPES = {
    "affiliation": {
        "id": "CorporateBody",
        "name": "Corporate Body",
    },
    "professionOrOccupation": {
        "id": "SubjectHeading",
        "name": "Subject Heading",
    },
    "placeOfBirth": {
        "id": "PlaceOrGeographicName",
        "name": "Place or Geographic Name",
    },
    "placeOfDeath": {
        "id": "PlaceOrGeographicName",
        "name": "Place or Geographic Name",
    },
    "placeOfActivity": {
        "id": "PlaceOrGeographicName",
        "name": "Place or Geographic Name",
    },
    "familialRelationship": {
        "id": "Person",
        "name": "Person",
    },
    "relatedPerson": {
        "id": "Person",
        "name": "Person",
    },
    "relatedTerm": {
        "id": "SubjectHeading",
        "name": "Subject Heading",
    },
    "broaderTermGeneral": {
        "id": "SubjectHeading",
        "name": "Subject Heading",
    },
    "broaderTermInstantial": {
        "id": "SubjectHeading",
        "name": "Subject Heading",
    },
    "broaderTermPartitive": {
        "id": "SubjectHeading",
        "name": "Subject Heading",
    },
    "isPartOf": {
        "id": "AuthorityResource",
        "name": "Normdatenressource",
    },
    "successor": {
        "id": "AuthorityResource",
        "name": "Normdatenressource",
    },
    "predecessor": {
        "id": "AuthorityResource",
        "name": "Normdatenressource",
    },
    "founder": {
        "id": "Person",
        "name": "Person",
    },
    "topic": {
        "id": "SubjectHeading",
        "name": "Subject Heading",
    },
    "isA": {
        "id": "SubjectHeading",
        "name": "Subject Heading",
    },
    "associatedPlace": {
        "id": "PlaceOrGeographicName",
        "name": "Place or Geographic Name",
    },
    "placeOfEvent": {
        "id": "PlaceOrGeographicName",
        "name": "Place or Geographic Name",
    },
    "organizerOrHost": {
        "id": "CorporateBody",
        "name": "Corporate Body",
    },
}


def get_property_proposals_from_index(
    entity_type: str | None = None,
    limit: int = 200,
) -> list[dict[str, str]]:
    body: dict[str, Any] = {
        "size": 0,
        "aggs": {
            "properties": {
                "terms": {
                    "field": "availableProperties",
                    "size": limit,
                }
            }
        },
    }

    if entity_type:
        allowed_types = GND_TYPE_ALIASES.get(entity_type, [entity_type])
        body["query"] = {"bool": {"filter": [{"terms": {"type": allowed_types}}]}}

    response = client.search(
        index=INDEX_NAME,
        body=body,
    )

    buckets = response.get("aggregations", {}).get("properties", {}).get("buckets", [])

    properties = []

    for bucket in buckets:
        prop_id = bucket.get("key")

        if not prop_id:
            continue

        properties.append(
            {
                "id": prop_id,
                "name": property_label(prop_id),
            }
        )

    return properties


def suggest_properties_from_index(
    prefix: str = "",
    entity_type: str | None = None,
    cursor: int = 0,
    limit: int = 10,
) -> list[dict[str, str]]:
    properties = get_property_proposals_from_index(
        entity_type=entity_type,
        limit=500,
    )

    normalized_prefix = prefix.strip().lower()

    if normalized_prefix:
        properties = [
            prop
            for prop in properties
            if normalized_prefix in prop["id"].lower()
            or normalized_prefix in prop["name"].lower()
        ]

    return properties[cursor : cursor + limit]


def get_property_values_from_record(
    record: dict[str, Any],
    prop_id: str,
):
    direct_value = record.get(prop_id)

    if direct_value is not None:
        return direct_value

    properties_flat = record.get("propertiesFlat", [])
    values = []

    for item in properties_flat:
        if not isinstance(item, dict):
            continue

        if item.get("id") == prop_id:
            value = item.get("value")

            if value is not None:
                values.append(value)

    return values


def extract_gnd_id(value: str) -> str | None:
    value = str(value).strip()

    uri_match = GND_URI_RE.match(value)

    if uri_match:
        return uri_match.group(1).strip().strip("/")

    if GND_ID_RE.match(value):
        return value

    return None


def resolve_gnd_entity(gnd_id: str) -> dict[str, Any] | None:
    """
    Resolves a GND ID against the local OpenSearch index and returns
    an OpenRefine-compatible reconciled entity object.
    """
    try:
        response = client.get(
            index=INDEX_NAME,
            id=gnd_id,
            ignore=[404],
        )
    except OpenSearchException:
        return None

    if not response or not response.get("found"):
        return None

    source = response.get("_source", {})

    name = source.get("preferredName") or source.get("name") or gnd_id

    entity_type = source.get("type")

    return {
        "id": gnd_id,
        "name": name,
        "type": format_entity_types(entity_type),
    }


def format_extend_value(
    raw_value: Any,
    content: str = "literal",
) -> dict[str, Any] | str:
    """
    Formats one value returned by the Extend API.

    content="literal":
      - GND references become OpenRefine reconciled entity objects.
      - normal values become readable strings.

    content="id":
      - GND references become bare GND IDs.
      - normal values become IDs/URIs/strings.
    """
    value = str(raw_value).strip()

    if not value:
        return ""

    gnd_id = extract_gnd_id(value)

    if gnd_id:
        if content == "id":
            return gnd_id

        entity = resolve_gnd_entity(gnd_id)

        if entity:
            return entity

        return {
            "id": gnd_id,
            "name": gnd_id,
            "type": [
                {
                    "id": "AuthorityResource",
                    "name": "Normdatenressource",
                }
            ],
        }

    vocab_label = resolve_gnd_vocab_uri(value)

    if vocab_label and content == "literal":
        return vocab_label

    return format_identifier_value(value) if content == "id" else value


def handle_extend_request(extend_request: dict) -> dict:
    """
    Processes an OpenRefine extend request.

    Expected input:
    {
      "ids": ["118540238"],
      "properties": [
        {"id": "preferredName"},
        {"id": "dateOfBirth"}
      ]
    }

    Expected output:
    {
      "meta": [...],
      "rows": {
        "118540238": {
          "preferredName": [{"str": "..."}],
          "professionOrOccupation": [
            {"id": "4053309-8", "name": "Schriftsteller", "type": [...]}
          ]
        }
      }
    }
    """
    ids = extend_request.get("ids", [])
    properties = extend_request.get("properties", [])

    if not isinstance(ids, list):
        ids = []

    if not isinstance(properties, list):
        properties = []

    meta = build_extend_meta(properties)
    rows = {}

    for gnd_id in ids:
        record = get_gnd_record_by_id(str(gnd_id))

        if record is None:
            rows[str(gnd_id)] = {}
            continue

        rows[str(gnd_id)] = build_extend_row(
            record=record,
            properties=properties,
        )

    return {
        "meta": meta,
        "rows": rows,
    }


def build_extend_meta(properties: list[dict]) -> list:
    """
    Builds metadata for requested properties.

    If a property usually returns GND entities, we announce a type.
    This helps OpenRefine treat returned values as entity-valued data.
    """
    meta = []

    for prop in properties:
        prop_id = prop.get("id")

        if not prop_id:
            continue

        meta_item = {
            "id": prop_id,
            "name": property_label(prop_id),
        }

        relation_type = RELATION_PROPERTY_TYPES.get(prop_id)

        if relation_type:
            meta_item["type"] = relation_type

        meta.append(meta_item)

    return meta


def build_extend_row(
    record: dict,
    properties: list[dict],
) -> dict:
    """
    Builds one row of property values for one GND record.
    """
    row = {}

    for prop in properties:
        prop_id = prop.get("id")

        if not prop_id:
            continue

        settings = get_extend_property_settings(prop)
        value = get_property_values_from_record(record, prop_id)

        values = format_extend_values(
            prop_id=prop_id,
            value=value,
            content=settings["content"],
        )

        values = apply_extend_limit(
            values=values,
            limit=settings["limit"],
        )

        row[prop_id] = values

    return row


def apply_extend_limit(
    values: list,
    limit: int,
) -> list:
    """
    Applies OpenRefine limit setting.
    limit = 0 means no limit.
    """
    if limit <= 0:
        return values

    return values[:limit]


def format_extend_values(
    prop_id: str,
    value,
    content: str = "literal",
) -> list:
    """
    Converts a value into OpenRefine extend cell format.

    content="id":
      Return raw identifiers / URIs as {"str": "..."}.

    content="literal":
      Return readable literals as {"str": "..."}, but return GND references
      as OpenRefine-compatible reconciled entity objects.
    """
    if value is None:
        return []

    if isinstance(value, list):
        result = []

        for item in value:
            result.extend(
                format_extend_values(
                    prop_id=prop_id,
                    value=item,
                    content=content,
                )
            )

        return deduplicate_extend_cells(result)

    if isinstance(value, dict):
        return format_extend_dict_value(
            value=value,
            content=content,
        )

    value_string = str(value)

    if content == "id":
        return [{"str": format_identifier_value(value_string)}]

    formatted_value = format_extend_value(
        raw_value=value_string,
        content=content,
    )

    if isinstance(formatted_value, dict):
        return [formatted_value]

    if not formatted_value:
        return []

    return [{"str": str(formatted_value)}]


def get_extend_property_settings(prop: dict) -> dict:
    """
    Extracts OpenRefine data extension settings for a requested property.

    Example:
    {
      "id": "geographicAreaCode",
      "settings": {
        "limit": "1",
        "content": "id"
      }
    }
    """
    settings = prop.get("settings", {})

    if not isinstance(settings, dict):
        settings = {}

    content = settings.get("content", "literal")

    if content not in {"id", "literal"}:
        content = "literal"

    limit = parse_extend_limit(settings.get("limit", 0))

    return {
        "content": content,
        "limit": limit,
    }


def parse_extend_limit(value) -> int:
    """
    Parses OpenRefine limit setting.
    0 means no limit.
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0

    if parsed < 0:
        return 0

    return parsed


def format_extend_dict_value(
    value: dict,
    content: str = "literal",
) -> list:
    """
    Formats dict values for OpenRefine extend output.
    """
    identifier = value.get("id") or value.get("@id") or value.get("uri")

    if content == "id":
        identifier_or_value = (
            identifier or value.get("value") or value.get("str") or value.get("name")
        )

        if identifier_or_value is None:
            return []

        return [{"str": format_identifier_value(str(identifier_or_value))}]

    if identifier is not None:
        formatted_identifier = format_extend_value(
            raw_value=identifier,
            content=content,
        )

        if isinstance(formatted_identifier, dict):
            return [formatted_identifier]

    label = (
        value.get("label")
        or value.get("name")
        or value.get("str")
        or value.get("value")
        or identifier
    )

    if label is None:
        return []

    formatted_label = format_extend_value(
        raw_value=label,
        content=content,
    )

    if isinstance(formatted_label, dict):
        return [formatted_label]

    return [{"str": str(formatted_label)}]


def deduplicate_extend_cells(values: list) -> list:
    """
    Deduplicates mixed OpenRefine extend cells.

    Also suppresses literal labels that duplicate the name of an entity object
    returned for the same property. This avoids returning both
    {"id": "4053309-8", "name": "Schriftsteller"} and {"str": "Schriftsteller"}.
    """
    entity_names = {
        item.get("name")
        for item in values
        if isinstance(item, dict) and item.get("id") and item.get("name")
    }

    seen = set()
    result = []

    for item in values:
        if isinstance(item, dict) and item.get("id"):
            key = ("entity", item.get("id"))
        elif isinstance(item, dict) and "str" in item:
            literal_value = item.get("str")

            if literal_value in entity_names:
                continue

            key = ("str", literal_value)
        else:
            key = ("raw", str(item))

        if key in seen:
            continue

        seen.add(key)
        result.append(item)

    return result


def format_identifier_value(value: str) -> str:
    """
    Formats identifier values for content='id'.
    Currently returns raw URI/identifier. This mirrors the ID/link mode.
    """
    gnd_id = extract_gnd_id(value)

    if gnd_id:
        return gnd_id

    return value


def resolve_extend_value(value: str) -> str | None:
    """
    Resolves values returned by /extend.

    Handles only non-entity labels here. GND entity URIs are handled by
    format_extend_value() so they can become reconciled entity objects.
    """
    resolved_vocab_value = resolve_gnd_vocab_uri(value)

    if resolved_vocab_value:
        return resolved_vocab_value

    return None


def resolve_gnd_uri_to_label(value: str) -> str | None:
    """
    Resolves a GND URI to the preferredName of the referenced local record.

    Kept for backwards compatibility. New Extend output should prefer
    resolve_gnd_entity()/format_extend_value() so OpenRefine receives
    reconciled entity objects instead of plain labels.
    """
    if not value.startswith(GND_URI_PREFIX):
        return None

    gnd_id = value.replace(GND_URI_PREFIX, "").strip("/")

    if not gnd_id:
        return None

    record = get_gnd_record_by_id(gnd_id)

    if not record:
        return None

    preferred_name = record.get("preferredName")

    if not preferred_name:
        return None

    return preferred_name
