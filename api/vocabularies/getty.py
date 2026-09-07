"""
GETTY_VOCAB: the VocabConfig instance for the Getty Art & Architecture
Thesaurus (AAT), mounted at /getty (see api/main.py).

Field naming mirrors importer/normalize_getty.py's normalized document
contract exactly: id, uri, preferredName, variantName, type, source,
parentString, parentStringAbbrev, scopeNote, broader, related, notation,
exactMatch, availableProperties, propertiesFlat.

Only AAT is wired up so far (importer/getty_vocab_specs.py's ULAN/TGN specs
are still stubs) - adding a second Getty vocabulary later means adding a
second VocabConfig instance here, not changing this one.
"""

from pathlib import Path
from typing import Any

from config import GETTY_INDEX_NAME
from importer.getty_vocab_specs import AAT_SPEC

GETTY_URI_PREFIX = AAT_SPEC.uri_prefix  # "http://vocab.getty.edu/aat/"

GETTY_ROOT_TYPE: dict[str, Any] = {"id": AAT_SPEC.key, "name": AAT_SPEC.display_name}
"""Root type prepended to every Getty candidate's type list by
format_entity_types(), analogous to AUTHORITY_RESOURCE_TYPE for GND."""

# AAT_SPEC.type_labels is the flat {local_type_name: english_label} shape
# shared with the importer. Restructure into GND_TYPE_LABELS's
# {name, broader: {id, name}} shape for the reconciliation API.
GETTY_TYPE_LABELS: dict[str, dict[str, Any]] = {
    type_key: {"name": label, "broader": GETTY_ROOT_TYPE}
    for type_key, label in AAT_SPEC.type_labels.items()
}

# OpenRefine manifest `defaultTypes`: root type plus one entry per AAT type.
GETTY_TYPES: tuple[dict[str, Any], ...] = (
    GETTY_ROOT_TYPE,
    *(
        {"id": type_key, "name": entry["name"], "broader": [GETTY_ROOT_TYPE]}
        for type_key, entry in GETTY_TYPE_LABELS.items()
    ),
)

# Getty's stored `type` values already are the canonical keys used above, so
# no coarse-type -> concrete-subtype aliasing is needed (unlike GND's
# Person/CorporateBody/... aliases).
GETTY_TYPE_ALIASES: dict[str, tuple[str, ...]] = {}

GETTY_SOURCE_FIELDS: tuple[str, ...] = (
    "id",
    "uri",
    "vocabulary",
    "source",
    "preferredName",
    "variantName",
    "type",
    "parentString",
    "parentStringAbbrev",
    "scopeNote",
    "broader",
    "related",
    "notation",
    "exactMatch",
    "availableProperties",
    "propertiesFlat",
)

# Getty has no date fields at all.
GETTY_DATE_PROPERTY_IDS: frozenset[str] = frozenset()

# normalize_getty.py always writes these as top-level fields (never only
# inside propertiesFlat), so the nested-join fallback can be skipped for
# them, mirroring GND_RELIABLE_TOP_LEVEL_PROPERTY_IDS.
GETTY_RELIABLE_TOP_LEVEL_PROPERTY_IDS: frozenset[str] = frozenset(
    {
        "parentString",
        "parentStringAbbrev",
        "scopeNote",
        "broader",
        "related",
        "notation",
        "exactMatch",
    }
)

GETTY_KEYWORD_FIELD_PROPERTY_IDS: dict[str, str] = {
    "id": "id",
    "uri": "uri",
    "notation": "notation",
}

GETTY_HIGH_PRIORITY_PROPERTY_IDS: frozenset[str] = frozenset({"id", "uri", "notation"})
GETTY_MEDIUM_PRIORITY_PROPERTY_IDS: frozenset[str] = frozenset({"broader", "related"})

GETTY_MULTI_MATCH_FIELDS: tuple[str, ...] = ("preferredName^5", "variantName^3", "id^10")
GETTY_FUZZY_FIELDS: tuple[str, ...] = ("preferredName^4", "variantName^3", "id^5")

# broader/related point at other Getty AAT concepts in the same index.
GETTY_RELATION_PROPERTY_TYPES: dict[str, dict[str, str]] = {
    "broader": {"id": "Concept", "name": "Concept"},
    "related": {"id": "Concept", "name": "Concept"},
}

# "id"/"uri" store the record's own identifier; unlike GND there's no
# separate "notation"-as-self-identifier case (notation is a genuine data
# property - a classification code - not a self-reference).
GETTY_SELF_IDENTIFIER_PROPERTY_IDS: frozenset[str] = frozenset({"id", "uri"})

GETTY_BASE_PREVIEW_FIELDS: tuple[str, ...] = (
    "preferredName",
    "variantName",
    "notation",
    "parentString",
    "scopeNote",
)

GETTY_FALLBACK_PREVIEW_FIELDS: tuple[str, ...] = ("broader", "related", "exactMatch", "uri")

GETTY_PROPERTY_LABEL_OVERRIDES: dict[str, str] = {
    "id": "AAT ID",
    "uri": "URI",
    "vocabulary": "Vocabulary",
    "preferredName": "Preferred Term",
    "variantName": "Variant Term",
    "type": "Type",
    "parentString": "Hierarchy Path",
    "parentStringAbbrev": "Hierarchy Path (abbreviated)",
    "scopeNote": "Scope Note",
    "broader": "Broader Concept",
    "related": "Related Concept",
    "notation": "Notation",
    "exactMatch": "Exact Match",
    "source": "Source",
}


def normalize_getty_identifier(value: str) -> str:
    """
    Normalizes a query/lookup value to the composite "aat/<subjectId>" form
    used as the OpenSearch document _id (see importer/normalize_getty.py).

    Accepts:
    - the composite id itself, e.g. "aat/300198841"
    - a bare AAT subject id, e.g. "300198841"
    - a full Getty AAT concept URI, e.g. "http://vocab.getty.edu/aat/300198841"
    """

    value = str(value or "").strip()

    if value.startswith(GETTY_URI_PREFIX):
        value = value[len(GETTY_URI_PREFIX) :].strip("/")
        return f"{AAT_SPEC.key}/{value}"

    value = value.strip("/")

    if value.startswith(f"{AAT_SPEC.key}/"):
        return value

    return f"{AAT_SPEC.key}/{value}" if value else value


def _build_getty_vocab():
    from api.vocabularies.base import VocabConfig

    return VocabConfig(
        key=AAT_SPEC.key,
        service_name="Local Getty AAT Reconciliation Service",
        index_name=GETTY_INDEX_NAME,
        identifier_space=GETTY_URI_PREFIX,
        schema_space=GETTY_URI_PREFIX,
        view_url_template=f"{GETTY_URI_PREFIX}{{{{id}}}}",
        uri_prefix=GETTY_URI_PREFIX,
        normalize_identifier=normalize_getty_identifier,
        route_prefix="/getty",
        types=GETTY_TYPES,
        type_labels=GETTY_TYPE_LABELS,
        type_aliases=GETTY_TYPE_ALIASES,
        root_type=GETTY_ROOT_TYPE,
        source_fields=GETTY_SOURCE_FIELDS,
        date_property_ids=GETTY_DATE_PROPERTY_IDS,
        reliable_top_level_property_ids=GETTY_RELIABLE_TOP_LEVEL_PROPERTY_IDS,
        keyword_field_property_ids=GETTY_KEYWORD_FIELD_PROPERTY_IDS,
        high_priority_property_ids=GETTY_HIGH_PRIORITY_PROPERTY_IDS,
        medium_priority_property_ids=GETTY_MEDIUM_PRIORITY_PROPERTY_IDS,
        multi_match_fields=GETTY_MULTI_MATCH_FIELDS,
        fuzzy_fields=GETTY_FUZZY_FIELDS,
        uses_date_signals=False,
        relation_property_types=GETTY_RELATION_PROPERTY_TYPES,
        self_identifier_property_ids=GETTY_SELF_IDENTIFIER_PROPERTY_IDS,
        preview_base_fields=GETTY_BASE_PREVIEW_FIELDS,
        preview_type_fields={},
        preview_fallback_fields=GETTY_FALLBACK_PREVIEW_FIELDS,
        preview_image_fields=(),
        preview_id_label="AAT",
        show_update_footer=False,
        property_registry_path=Path("config/getty_properties.json"),
        property_label_overrides=GETTY_PROPERTY_LABEL_OVERRIDES,
        vocab_labels_path=None,
    )


GETTY_VOCAB = _build_getty_vocab()
