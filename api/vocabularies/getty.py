"""
Getty vocabulary configurations.

This module exposes dedicated VocabConfig instances for:
- /aat  (AAT only, used internally/for tests)
- /ulan (ULAN only, used internally/for tests)
- /tgn  (TGN only, used internally/for tests)
- /getty (all enabled Getty vocabularies - the only mounted endpoint)

Only `GETTY_VOCAB` (= `ALL_GETTY_VOCAB`) is mounted as a route in api/main.py.
Its `defaultTypes` list is what OpenRefine's type dropdown shows: a root
"Search all Vocabs" entry plus one entry per vocabulary ("AAT search",
"ULAN search", "TGN search"), so users pick a vocabulary via the type
filter on a single service URL instead of choosing between separate URLs.
"""

from pathlib import Path
from typing import Any, Callable

from config import GETTY_INDEX_NAME, GETTY_VOCABULARIES
from importer.getty_vocab_specs import GettyVocabSpec, get_vocab_spec

GETTY_NAMESPACE_PREFIX = "http://vocab.getty.edu/"
GETTY_VIEW_URL_TEMPLATE = "http://vocab.getty.edu/page/{{id}}"

# Reconciliation API 0.2 defines `schemaSpace` as a URI identifying the *type*
# of the entities returned - a different concept from `identifierSpace` (the
# namespace of the entity identifiers). All Getty vocabulary records are
# published as SKOS concepts, so skos:Concept is the correct schema space.
GETTY_SCHEMA_SPACE = "http://www.w3.org/2004/02/skos/core#Concept"

ALL_GETTY_KEYS: tuple[str, ...] = ("aat", "ulan", "tgn")


def _specs_from_keys(keys: list[str] | tuple[str, ...]) -> tuple[GettyVocabSpec, ...]:
    seen: set[str] = set()
    specs: list[GettyVocabSpec] = []

    for key in keys:
        normalized = key.strip().lower()

        if not normalized or normalized in seen:
            continue

        specs.append(get_vocab_spec(normalized))
        seen.add(normalized)

    return tuple(specs)


def _enabled_all_specs() -> tuple[GettyVocabSpec, ...]:
    env_specs = _specs_from_keys(tuple(GETTY_VOCABULARIES))

    if env_specs:
        return env_specs

    return _specs_from_keys(ALL_GETTY_KEYS)


def _build_normalizer(specs: tuple[GettyVocabSpec, ...]) -> Callable[[str], str]:
    primary = specs[0]

    def _normalize(value: str) -> str:
        normalized = str(value or "").strip()

        for spec in specs:
            if normalized.startswith(spec.uri_prefix):
                subject_id = normalized[len(spec.uri_prefix) :].strip("/")
                return f"{spec.key}/{subject_id}" if subject_id else normalized

        normalized = normalized.strip("/")

        for spec in specs:
            if normalized.startswith(f"{spec.key}/"):
                return normalized

        if normalized.isdigit():
            return f"{primary.key}/{normalized}"

        return normalized

    return _normalize


def _type_compatibility_aliases() -> dict[str, tuple[str, ...]]:
    return {
        "ulan:Person": ("ulan:PersonConcept", "ulan:UnknownPersonConcept"),
        "ulan:Group": ("ulan:GroupConcept",),
        "tgn:Place": (
            "tgn:AdminPlaceConcept",
            "tgn:PhysPlaceConcept",
            "tgn:PhysAdminPlaceConcept",
        ),
        "tgn:AdminPlace": ("tgn:AdminPlaceConcept",),
        "tgn:PhysPlace": ("tgn:PhysPlaceConcept", "tgn:PhysAdminPlaceConcept"),
    }


COMBINED_ROOT_TYPE_NAME = "Search all Vocabs"

COMBINED_VOCAB_TYPE_NAMES: dict[str, str] = {
    "aat": "AAT search",
    "ulan": "ULAN search",
    "tgn": "TGN search",
}


def _build_type_structures(
    specs: tuple[GettyVocabSpec, ...],
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...], dict[str, tuple[str, ...]], dict[str, dict[str, Any]]]:
    is_combined_vocab = len(specs) > 1

    if len(specs) == 1:
        root_type = {"id": specs[0].key, "name": specs[0].display_name}
    else:
        root_type = {"id": "getty", "name": COMBINED_ROOT_TYPE_NAME}

    if is_combined_vocab:
        vocab_roots: dict[str, dict[str, Any]] = {
            spec.key: {
                "id": spec.key,
                "name": COMBINED_VOCAB_TYPE_NAMES.get(spec.key, spec.display_name),
            }
            for spec in specs
        }
    else:
        vocab_roots = {
            spec.key: {"id": spec.key, "name": spec.display_name} for spec in specs
        }

    type_labels: dict[str, dict[str, Any]] = {}
    type_aliases: dict[str, tuple[str, ...]] = {}
    local_type_to_namespaced: dict[str, list[str]] = {}
    default_types: list[dict[str, Any]] = [root_type]

    if is_combined_vocab:
        for spec in specs:
            vocab_root = vocab_roots[spec.key]
            default_types.append(
                {
                    "id": vocab_root["id"],
                    "name": vocab_root["name"],
                    "broader": [root_type],
                }
            )

    for spec in specs:
        vocab_root = vocab_roots[spec.key]
        namespaced_types: list[str] = []

        for local_type, label in spec.type_labels.items():
            namespaced = f"{spec.key}:{local_type}"
            namespaced_types.append(namespaced)

            if is_combined_vocab:
                # Collapse every concrete stored type (e.g. "aat:Concept",
                # "ulan:PersonConcept", "tgn:AdminPlaceConcept") onto its
                # vocab-level type in the combined /getty vocab, so results
                # and the type facet only ever show "AAT search"/"ULAN
                # search"/"TGN search" - never the underlying concrete
                # subtypes.
                type_labels[namespaced] = {
                    "id": vocab_root["id"],
                    "name": vocab_root["name"],
                    "broader": root_type,
                }
            else:
                type_labels[namespaced] = {"name": label, "broader": vocab_root}

            type_aliases[namespaced] = (namespaced,)
            local_type_to_namespaced.setdefault(local_type, []).append(namespaced)

            if not is_combined_vocab:
                default_types.append(
                    {
                        "id": namespaced,
                        "name": label,
                        "broader": [vocab_root],
                    }
                )

        if namespaced_types:
            type_aliases[spec.key] = tuple(namespaced_types)

    for local_type, namespaced_values in local_type_to_namespaced.items():
        type_aliases[local_type] = tuple(namespaced_values)

    existing_type_ids = set(type_labels.keys())

    for alias_id, concrete_ids in _type_compatibility_aliases().items():
        filtered = tuple(type_id for type_id in concrete_ids if type_id in existing_type_ids)

        if filtered:
            type_aliases[alias_id] = filtered

    return root_type, tuple(default_types), type_aliases, type_labels


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
    "nationality",
    "role",
    "biography",
    "placeType",
    "coordinates",
    "gender",
    "birthPlace",
    "deathPlace",
    "birthDate",
    "deathDate",
    "location",
    "startDate",
    "endDate",
    "availableProperties",
    "propertiesFlat",
)

GETTY_DATE_PROPERTY_IDS: frozenset[str] = frozenset()

GETTY_RELIABLE_TOP_LEVEL_PROPERTY_IDS: frozenset[str] = frozenset(
    {
        "parentString",
        "parentStringAbbrev",
        "scopeNote",
        "broader",
        "related",
        "notation",
        "exactMatch",
        "nationality",
        "role",
        "biography",
        "placeType",
        "coordinates",
        "gender",
        "birthPlace",
        "deathPlace",
        "birthDate",
        "deathDate",
        "location",
        "startDate",
        "endDate",
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
    "id": "Getty ID",
    "uri": "URI",
    "vocabulary": "Vocabulary",
    "preferredName": "Preferred Term",
    "variantName": "Variant Terms",
    "type": "Type",
    "parentString": "Parent Hierarchy",
    "parentStringAbbrev": "Parent Hierarchy (abbreviated)",
    "scopeNote": "Descriptive Notes",
    "broader": "Broader Concept",
    "related": "Related Concept",
    "notation": "Notation",
    "exactMatch": "Exact Match",
    "source": "Source",
    "nationality": "Nationalities",
    "role": "Roles",
    "biography": "Biographies",
    "placeType": "Place Types",
    "coordinates": "Coordinates",
    "gender": "Gender",
    "birthPlace": "Birth Place",
    "deathPlace": "Death Place",
    "birthDate": "Birth Date",
    "deathDate": "Death Date",
    "location": "Location",
    "startDate": "Start Date",
    "endDate": "End Date",
}


def _build_getty_vocab(
    *,
    config_key: str,
    service_name: str,
    route_prefix: str,
    specs: tuple[GettyVocabSpec, ...],
    fixed_vocabulary: str | None,
):
    from api.vocabularies.base import VocabConfig

    root_type, default_types, type_aliases, type_labels = _build_type_structures(specs)
    primary = specs[0]
    relation_type_id = f"{primary.key}:{primary.default_type_key}"
    relation_type_name = primary.type_labels.get(primary.default_type_key, primary.default_type_key)

    # nationality/role/placeType always reference AAT concepts regardless of
    # which vocab is being reconciled (ULAN nationality/role and TGN place
    # type triples always point at aat/* URIs) - so their announced extend
    # type should describe AAT specifically, not whichever spec happens to
    # be "primary" for this particular VocabConfig.
    aat_spec = get_vocab_spec("aat")
    aat_relation_type_id = f"{aat_spec.key}:{aat_spec.default_type_key}"
    aat_relation_type_name = aat_spec.type_labels.get(
        aat_spec.default_type_key, aat_spec.default_type_key
    )

    if len(specs) == 1:
        identifier_space = primary.uri_prefix
        preview_id_label = primary.key.upper()
    else:
        identifier_space = GETTY_NAMESPACE_PREFIX
        preview_id_label = "Getty"

    return VocabConfig(
        key=config_key,
        service_name=service_name,
        index_name=GETTY_INDEX_NAME,
        identifier_space=identifier_space,
        schema_space=GETTY_SCHEMA_SPACE,
        view_url_template=GETTY_VIEW_URL_TEMPLATE,
        uri_prefix=GETTY_NAMESPACE_PREFIX,
        normalize_identifier=_build_normalizer(specs),
        route_prefix=route_prefix,
        types=default_types,
        type_labels=type_labels,
        type_aliases=type_aliases,
        root_type=root_type,
        source_fields=GETTY_SOURCE_FIELDS,
        date_property_ids=GETTY_DATE_PROPERTY_IDS,
        reliable_top_level_property_ids=GETTY_RELIABLE_TOP_LEVEL_PROPERTY_IDS,
        keyword_field_property_ids=GETTY_KEYWORD_FIELD_PROPERTY_IDS,
        high_priority_property_ids=GETTY_HIGH_PRIORITY_PROPERTY_IDS,
        medium_priority_property_ids=GETTY_MEDIUM_PRIORITY_PROPERTY_IDS,
        multi_match_fields=GETTY_MULTI_MATCH_FIELDS,
        fuzzy_fields=GETTY_FUZZY_FIELDS,
        uses_date_signals=False,
        fixed_vocabulary=fixed_vocabulary,
        relation_property_types={
            "broader": {"id": relation_type_id, "name": relation_type_name},
            "related": {"id": relation_type_id, "name": relation_type_name},
            "nationality": {"id": aat_relation_type_id, "name": aat_relation_type_name},
            "role": {"id": aat_relation_type_id, "name": aat_relation_type_name},
            "placeType": {"id": aat_relation_type_id, "name": aat_relation_type_name},
        },
        self_identifier_property_ids=GETTY_SELF_IDENTIFIER_PROPERTY_IDS,
        preview_base_fields=GETTY_BASE_PREVIEW_FIELDS,
        preview_type_fields={},
        preview_fallback_fields=GETTY_FALLBACK_PREVIEW_FIELDS,
        preview_image_fields=(),
        preview_id_label=preview_id_label,
        show_update_footer=False,
        property_registry_path=Path("config/getty_properties.json"),
        property_label_overrides=GETTY_PROPERTY_LABEL_OVERRIDES,
        vocab_labels_path=None,
    )


AAT_VOCAB = _build_getty_vocab(
    config_key="aat",
    service_name="AAT search",
    route_prefix="/aat",
    specs=_specs_from_keys(("aat",)),
    fixed_vocabulary="aat",
)

ULAN_VOCAB = _build_getty_vocab(
    config_key="ulan",
    service_name="ULAN search",
    route_prefix="/ulan",
    specs=_specs_from_keys(("ulan",)),
    fixed_vocabulary="ulan",
)

TGN_VOCAB = _build_getty_vocab(
    config_key="tgn",
    service_name="TGN search",
    route_prefix="/tgn",
    specs=_specs_from_keys(("tgn",)),
    fixed_vocabulary="tgn",
)

ALL_GETTY_VOCAB = _build_getty_vocab(
    config_key="getty",
    service_name="OpenSearch Reconciliation API for Getty Vocabularies",
    route_prefix="/getty",
    specs=_enabled_all_specs(),
    fixed_vocabulary=None,
)

# Canonical combined Getty vocabulary config - the only one mounted as a route.
GETTY_VOCAB = ALL_GETTY_VOCAB
