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
    type_labels={},
    default_type_key="Concept",
)

TGN_SPEC = GettyVocabSpec(
    key="tgn",
    display_name="Getty Thesaurus of Geographic Names",
    uri_prefix="http://vocab.getty.edu/tgn/",
    file_prefix="TGNOut",
    type_labels={},
    default_type_key="Concept",
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
