import json
from pathlib import Path
from typing import Any

from api.vocabularies.base import VocabConfig
from api.vocabularies.gnd import GND_VOCAB

# Kept for backward compatibility with existing imports; GND_VOCAB.property_
# registry_path (see api/vocabularies/gnd.py) is now the single source of
# truth for the GND registry file location.
REGISTRY_PATH = Path("config/gnd_properties.json")


def load_property_registry(
    registry_path: Path | None = None,
) -> dict[str, list[dict[str, str]]]:
    registry_path = registry_path or REGISTRY_PATH

    if not registry_path.exists():
        return {}

    with registry_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def get_registry_properties_for_type(
    entity_type: str | None = None,
    limit: int = 200,
    vocab: VocabConfig = GND_VOCAB,
) -> list[dict[str, str]]:
    registry = load_property_registry(vocab.property_registry_path)

    if entity_type and entity_type in registry:
        return registry[entity_type][:limit]

    # Fallback: merge all known properties
    merged: dict[str, dict[str, str]] = {}

    for properties in registry.values():
        for prop in properties:
            prop_id = prop.get("id")

            if not prop_id:
                continue

            merged[prop_id] = {
                "id": prop_id,
                "name": prop.get("name", prop_id),
            }

    return list(merged.values())[:limit]


def suggest_registry_properties(
    prefix: str = "",
    entity_type: str | None = None,
    cursor: int = 0,
    limit: int = 10,
    vocab: VocabConfig = GND_VOCAB,
) -> list[dict[str, str]]:
    properties = get_registry_properties_for_type(
        entity_type=entity_type,
        limit=1000,
        vocab=vocab,
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
