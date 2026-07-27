from typing import Any

from api.services.property_labels import property_label
from api.services.search import GND_TYPE_ALIASES, INDEX_NAME, client


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

        body["query"] = {
            "bool": {
                "filter": [
                    {
                        "terms": {
                            "type": allowed_types
                        }
                    }
                ]
            }
        }

    response = client.search(
        index=INDEX_NAME,
        body=body,
    )

    buckets = (
        response
        .get("aggregations", {})
        .get("properties", {})
        .get("buckets", [])
    )

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