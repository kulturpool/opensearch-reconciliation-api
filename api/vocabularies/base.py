"""
VocabConfig: single source of truth describing one reconciliation vocabulary
(GND, Getty AAT, ...).

The search/scoring/extend/preview code in api/services/* is written against
this config object (with a GND-default parameter for backward compatibility)
instead of hardcoded GND constants, so a new vocabulary - e.g. Getty AAT -
can be added as a new VocabConfig instance instead of new code paths.

All collections are tuples/frozensets (not list/dict-with-mutable-values)
where practical, precomputed once at import time, matching the existing
module-level constants they replace (e.g. api/services/search.py
DATE_PROPERTY_IDS, RELIABLE_TOP_LEVEL_PROPERTY_IDS, ...).
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class VocabConfig:
    # -------------------------------------------------------------------
    # Identity
    # -------------------------------------------------------------------
    key: str
    """Short vocabulary key, e.g. "gnd", "aat". Used as an index/route/id prefix."""

    service_name: str
    """Human-readable service name for the OpenRefine manifest."""

    index_name: str
    """OpenSearch index (or alias) name backing this vocabulary."""

    identifier_space: str
    schema_space: str

    view_url_template: str
    """OpenRefine manifest `view.url`, e.g. "https://d-nb.info/gnd/{{id}}"."""

    uri_prefix: str
    """Prefix stripped/added when normalizing IDs <-> URIs, e.g. "https://d-nb.info/gnd/"."""

    normalize_identifier: Callable[[str], str]
    """Normalizes a query/lookup value to this vocabulary's bare ID form."""

    route_prefix: str = ""
    """Path prefix this vocab's router is mounted at in api/main.py, e.g.
    "" for GND (mounted at root) or "/getty" for Getty. Used to build the
    absolute suggest/extend/preview service URLs advertised in the OpenRefine
    manifest."""

    # -------------------------------------------------------------------
    # Types
    # -------------------------------------------------------------------
    types: tuple[dict[str, Any], ...] = ()
    """Top-level `defaultTypes` list for the OpenRefine manifest."""

    type_labels: dict[str, dict[str, Any]] = field(default_factory=dict)
    """Per-type {name, broader} label lookup, e.g. GND_TYPE_LABELS."""

    type_aliases: dict[str, tuple[str, ...]] = field(default_factory=dict)
    """Coarse type -> concrete sub-type list, e.g. GND_TYPE_ALIASES."""

    root_type: dict[str, Any] | None = None
    """Root type object (e.g. AUTHORITY_RESOURCE_TYPE) that
    format_entity_types() always prepends to every candidate's type list.
    Set to None for vocabularies with no such catch-all root type."""

    # -------------------------------------------------------------------
    # Search / query building (api/services/search.py)
    # -------------------------------------------------------------------
    source_fields: tuple[str, ...] = ()
    """OpenSearch `_source.includes` fields fetched per candidate."""

    date_property_ids: frozenset[str] = frozenset()
    reliable_top_level_property_ids: frozenset[str] = frozenset()
    keyword_field_property_ids: dict[str, str] = field(default_factory=dict)
    high_priority_property_ids: frozenset[str] = frozenset()
    medium_priority_property_ids: frozenset[str] = frozenset()

    id_boost: float = 20.0
    preferred_keyword_boost: float = 15.0
    preferred_phrase_boost: float = 12.0
    variant_keyword_boost: float = 10.0
    variant_phrase_boost: float = 8.0
    multi_match_fields: tuple[str, ...] = ()
    multi_match_boost: float = 5.0
    fuzzy_fields: tuple[str, ...] = ()
    fuzzy_max_expansions: int = 20
    fuzzy_max_terms: int = 6

    uses_date_signals: bool = True
    """Whether score_date_signals()/dateOf* handling applies to this vocab."""

    # -------------------------------------------------------------------
    # Extend (api/services/properties.py)
    # -------------------------------------------------------------------
    relation_property_types: dict[str, dict[str, str]] = field(default_factory=dict)
    self_identifier_property_ids: frozenset[str] = frozenset()

    # -------------------------------------------------------------------
    # Preview (api/services/preview.py)
    # -------------------------------------------------------------------
    preview_base_fields: tuple[str, ...] = ()
    preview_type_fields: dict[str, tuple[str, ...]] = field(default_factory=dict)
    preview_fallback_fields: tuple[str, ...] = ()
    preview_image_fields: tuple[str, ...] = ()
    preview_id_label: str = "GND"
    """Short label shown next to the id in the preview HTML, e.g. "GND 118540238"."""
    show_update_footer: bool = True
    """Whether to show the "Letzte Aktualisierung der Daten" footer, sourced
    from data/state/update_state.json (GND's OAI update tracking - not
    meaningful for vocabularies without an analogous update mechanism)."""

    # -------------------------------------------------------------------
    # Property registry / labels
    # -------------------------------------------------------------------
    property_registry_path: Path | None = None
    property_label_overrides: dict[str, str] = field(default_factory=dict)
    vocab_labels_path: Path | None = None
