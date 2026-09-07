"""
Per-vocabulary specs for Getty Vocabulary Program explicit exports.

v1 ships AAT only. ULAN/TGN entries are intentionally left as stubs so that
adding a new Getty vocabulary later is "fill in one spec + one reindex"
(FINAL PLAN section 1). The type-label maps defined here are the single
source of truth reused by both the importer/indexer (this module,
`normalize_getty.py`) and the reconciliation API (`api/vocabularies/getty.py`,
Phase 5) - mirrors how `api/gnd_types.py` serves both layers for GND.
"""

from dataclasses import dataclass, field

RDF_TYPE_PREDICATE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"

GVP_NS = "http://vocab.getty.edu/ontology#"
SKOS_NS = "http://www.w3.org/2004/02/skos/core#"
SKOSXL_NS = "http://www.w3.org/2008/05/skos-xl#"
DC11_NS = "http://purl.org/dc/elements/1.1/"
DCT_NS = "http://purl.org/dc/terms/"

# Predicates shared across Getty vocabularies.
PRED_PARENT_STRING = f"{GVP_NS}parentString"
PRED_PARENT_STRING_ABBREV = f"{GVP_NS}parentStringAbbrev"
PRED_IDENTIFIER = f"{DC11_NS}identifier"
PRED_PREF_LABEL_GVP = f"{GVP_NS}prefLabelGVP"
PRED_PREF_LABEL_LOC = f"{GVP_NS}prefLabelLoC"
PRED_XL_PREF_LABEL = f"{SKOSXL_NS}prefLabel"
PRED_XL_ALT_LABEL = f"{SKOSXL_NS}altLabel"
PRED_XL_LITERAL_FORM = f"{SKOSXL_NS}literalForm"
PRED_LANGUAGE = f"{DCT_NS}language"
PRED_SCOPE_NOTE = f"{SKOS_NS}scopeNote"
PRED_NOTATION = f"{SKOS_NS}notation"
PRED_EXACT_MATCH = f"{SKOS_NS}exactMatch"
PRED_PREF_LABEL_PLAIN = f"{SKOS_NS}prefLabel"
PRED_BROADER_PREFERRED = f"{GVP_NS}broaderPreferred"
RDF_VALUE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#value"
RDF_SUBJECT = "http://www.w3.org/1999/02/22-rdf-syntax-ns#subject"
RDF_OBJECT = "http://www.w3.org/1999/02/22-rdf-syntax-ns#object"
RDF_PREDICATE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#predicate"

# ULAN-specific predicates (nationality/role/biography). ULAN's explicit
# export models these on a companion "-agent"-suffixed resource for
# nationality/biography (verified: `ulan/<id>-agent`), but directly on the
# plain subject for agent types/roles (verified: `ulan/<id>`).
PRED_NATIONALITY_PREFERRED = f"{GVP_NS}nationalityPreferred"
PRED_NATIONALITY_NON_PREFERRED = f"{GVP_NS}nationalityNonPreferred"
PRED_AGENT_TYPE_PREFERRED = f"{GVP_NS}agentTypePreferred"
PRED_AGENT_TYPE_NON_PREFERRED = f"{GVP_NS}agentTypeNonPreferred"
PRED_BIOGRAPHY_PREFERRED = f"{GVP_NS}biographyPreferred"
PRED_BIOGRAPHY_NON_PREFERRED = f"{GVP_NS}biographyNonPreferred"
PRED_SCHEMA_DESCRIPTION = "http://schema.org/description"

# TGN-specific predicates (coordinates/place types). Coordinates are modeled
# on a companion "-place"-suffixed resource (verified: `tgn/<id>-place`);
# place types are direct triples on the plain subject.
PRED_GEO_LAT = "http://www.w3.org/2003/01/geo/wgs84_pos#lat"
PRED_GEO_LONG = "http://www.w3.org/2003/01/geo/wgs84_pos#long"
PRED_PLACE_TYPE_PREFERRED = f"{GVP_NS}placeTypePreferred"


@dataclass(frozen=True)
class GettyVocabSpec:
    """
    Static, per-vocabulary configuration for the Getty importer/indexer.
    """

    key: str
    """Short vocabulary key, e.g. "aat". Also used as the reconciliation
    `vocabulary` field value and as the id prefix (`<key>/<subjectId>`)."""

    display_name: str
    """Human-readable vocabulary name, e.g. "Getty Art & Architecture
    Thesaurus"."""

    uri_prefix: str
    """Concept URI prefix, e.g. "http://vocab.getty.edu/aat/"."""

    file_prefix: str
    """Explicit export filename prefix, e.g. "AATOut"."""

    type_labels: dict[str, str] = field(default_factory=dict)
    """Maps the RDF type's local name (e.g. "Concept") to a human-readable
    English label (e.g. "Concept")."""

    default_type_key: str = "Concept"
    """Local type name used when a subject has no recognized rdf:type."""

    notation_file_suffix: str | None = "_Notations.nt"
    """Filename suffix for skos:notation triples, if available."""

    exact_match_file_suffix: str | None = "_LCSHAlignment.nt"
    """Filename suffix for exact-match alignment triples, if available."""

    nationality_file_suffix: str | None = None
    """Filename suffix for gvp:nationalityPreferred/NonPreferred triples
    (ULAN only), if available."""

    agent_type_file_suffix: str | None = None
    """Filename suffix for gvp:agentTypePreferred/NonPreferred ("role")
    triples (ULAN only), if available."""

    biography_file_suffix: str | None = None
    """Filename suffix for gvp:biographyPreferred/NonPreferred + biography
    schema:description triples (ULAN only), if available."""

    coordinates_file_suffix: str | None = None
    """Filename suffix for wgs84 lat/long triples (TGN only), if available."""

    place_type_file_suffix: str | None = None
    """Filename suffix for gvp:placeTypePreferred triples (TGN only), if
    available."""


AAT_TYPE_LABELS: dict[str, str] = {
    "Concept": "Concept",
    "Facet": "Facet",
    "Hierarchy": "Hierarchy",
    "GuideTerm": "Guide Term",
    "ObsoleteSubject": "Obsolete Subject",
}

AAT_SPEC = GettyVocabSpec(
    key="aat",
    display_name="Getty Art & Architecture Thesaurus",
    uri_prefix="http://vocab.getty.edu/aat/",
    file_prefix="AATOut",
    type_labels=AAT_TYPE_LABELS,
    default_type_key="Concept",
)

# Design-prepared stubs (out of scope for v1, per FINAL PLAN section 8).
# Enabling either later requires: filling in uri_prefix/file_prefix/
# type_labels here, adding the matching entry to
# `importer.download_getty.GETTY_SOURCES`, and one reindex.
ULAN_SPEC = GettyVocabSpec(
    key="ulan",
    display_name="Getty Union List of Artist Names",
    uri_prefix="http://vocab.getty.edu/ulan/",
    file_prefix="ULANOut",
    type_labels={
        "PersonConcept": "Person",
        "UnknownPersonConcept": "Unknown Person",
        "GroupConcept": "Group",
        "ObsoleteSubject": "Obsolete Subject",
        "GuideTerm": "Guide Term",
        "Facet": "Facet",
    },
    default_type_key="PersonConcept",
    notation_file_suffix=None,
    exact_match_file_suffix="_LOCAlignment.nt",
    nationality_file_suffix="_Nationality.nt",
    agent_type_file_suffix="_AgentTypes.nt",
    biography_file_suffix="_Biographies.nt",
)

TGN_SPEC = GettyVocabSpec(
    key="tgn",
    display_name="Getty Thesaurus of Geographic Names",
    uri_prefix="http://vocab.getty.edu/tgn/",
    file_prefix="TGNOut",
    type_labels={
        "AdminPlaceConcept": "Administrative Place",
        "PhysPlaceConcept": "Physical Place",
        "PhysAdminPlaceConcept": "Administrative + Physical Place",
        "ObsoleteSubject": "Obsolete Subject",
        "GuideTerm": "Guide Term",
        "Facet": "Facet",
    },
    default_type_key="AdminPlaceConcept",
    notation_file_suffix=None,
    exact_match_file_suffix=None,
    coordinates_file_suffix="_Coordinates.nt",
    place_type_file_suffix="_PlaceTypes.nt",
)

GETTY_VOCAB_SPECS: dict[str, GettyVocabSpec] = {
    "aat": AAT_SPEC,
    "ulan": ULAN_SPEC,
    "tgn": TGN_SPEC,
}


def get_vocab_spec(key: str) -> GettyVocabSpec:
    if key not in GETTY_VOCAB_SPECS:
        valid = ", ".join(sorted(GETTY_VOCAB_SPECS.keys()))
        raise ValueError(f"Unknown Getty vocabulary: {key}. Valid: {valid}")

    return GETTY_VOCAB_SPECS[key]


def local_name(uri: str) -> str:
    """
    Returns the local name (last path/fragment segment) of a URI, e.g.
    "http://vocab.getty.edu/ontology#Concept" -> "Concept".
    """

    for separator in ("#", "/"):
        if separator in uri:
            return uri.rsplit(separator, 1)[-1]

    return uri
