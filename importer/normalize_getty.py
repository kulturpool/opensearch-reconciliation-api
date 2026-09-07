"""
Two-pass normalizer for Getty Vocabulary Program explicit exports.

Getty's SKOS-XL indirection means preferred/variant labels are NOT direct
literals on the concept subject - they point at separate term-node
resources (see repo memory "GETTY AAT EXPLICIT EXPORT — VERIFIED FILE
SCHEMA"). This requires a two-pass join:

Pass 1: stream the "join" files once each and build in-memory lookup dicts
(term-node id -> literal text, scopeNote-node id -> text, child concept id
-> [broader parent ids], concept id -> [related ids], concept id ->
notation, concept id -> [exactMatch URIs]).

Pass 2: stream the (large, subject-sorted) `*_1Subjects.nt` file
subject-by-subject and combine each subject's own triples with the pass-1
lookup dicts to build one normalized reconciliation document per subject.
`*_ObsoleteSubjects.nt` is normalized separately (simpler, self-contained
shape - no SKOS-XL indirection).

Field names deliberately mirror the GND normalized document contract (id,
uri, preferredName, variantName, type, source, availableProperties,
propertiesFlat) so existing search/scoring/extend/preview code is reusable
as-is (FINAL PLAN section 4).
"""

import argparse
import json
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Add parent directory to path to allow imports from config
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import GETTY_RAW_DIR
from importer.getty_vocab_specs import (
    GETTY_VOCAB_SPECS,
    GettyVocabSpec,
    PRED_BROADER_PREFERRED,
    PRED_EXACT_MATCH,
    PRED_IDENTIFIER,
    PRED_NOTATION,
    PRED_PARENT_STRING,
    PRED_PARENT_STRING_ABBREV,
    PRED_PREF_LABEL_GVP,
    PRED_PREF_LABEL_LOC,
    PRED_PREF_LABEL_PLAIN,
    PRED_SCOPE_NOTE,
    PRED_XL_ALT_LABEL,
    PRED_XL_LITERAL_FORM,
    PRED_XL_PREF_LABEL,
    RDF_OBJECT,
    RDF_PREDICATE,
    RDF_SUBJECT,
    RDF_TYPE_PREDICATE,
    RDF_VALUE,
    get_vocab_spec,
    local_name,
)
from importer.ntriples import Triple, iter_subject_groups, iter_triples

# Explicit export filename suffixes (appended to `vocab.file_prefix`).
FILE_SUBJECTS = "_1Subjects.nt"
FILE_TERMS = "_2Terms.nt"
FILE_SCOPE_NOTES = "_ScopeNotes.nt"
FILE_HIERARCHICAL_RELS = "_HierarchicalRels.nt"
FILE_ASSOCIATIVE_RELS = "_AssociativeRels.nt"
FILE_NOTATIONS = "_Notations.nt"
FILE_LCSH_ALIGNMENT = "_LCSHAlignment.nt"
FILE_OBSOLETE_SUBJECTS = "_ObsoleteSubjects.nt"

# Literal (top-level) properties: exposed both as direct fields (candidates
# for reliable_top_level_property_ids in Phase 5's GETTY_VOCAB) and mirrored
# into propertiesFlat for generic reconciliation-extend code reuse.
LITERAL_PROPERTY_FIELDS = ("parentString", "parentStringAbbrev", "scopeNote", "notation")


def vocab_file(raw_dir: Path, vocab: GettyVocabSpec, suffix: str) -> Path:
    return raw_dir / vocab.key / f"{vocab.file_prefix}{suffix}"


@dataclass
class GettyLookups:
    term_literal: dict[str, tuple[str, str | None]]
    subject_term_refs: dict[str, dict[str, list[str]]]
    scope_note_text: dict[str, tuple[str, str | None]]
    subject_scope_notes: dict[str, list[str]]
    broader: dict[str, list[str]]
    related: dict[str, list[str]]
    notation: dict[str, str]
    exact_match: dict[str, list[str]]


def build_terms_index(
    path: Path,
) -> tuple[dict[str, tuple[str, str | None]], dict[str, dict[str, list[str]]]]:
    """
    Single pass over `*_2Terms.nt` building:
    - term_literal: term-node URI -> (literalForm text, lang)
    - subject_refs: concept URI -> {"gvp": [...], "loc": [...], "pref": [...], "alt": [...]}
      (lists of term-node URIs, joinable via term_literal above)
    """

    term_literal: dict[str, tuple[str, str | None]] = {}
    subject_refs: dict[str, dict[str, list[str]]] = {}

    predicate_bucket = {
        PRED_PREF_LABEL_GVP: "gvp",
        PRED_PREF_LABEL_LOC: "loc",
        PRED_XL_PREF_LABEL: "pref",
        PRED_XL_ALT_LABEL: "alt",
    }

    for triple in iter_triples(path):
        if triple.predicate == PRED_XL_LITERAL_FORM and triple.is_literal:
            term_literal[triple.subject] = (triple.obj, triple.lang)
            continue

        bucket = predicate_bucket.get(triple.predicate)

        if bucket is not None and not triple.is_literal:
            refs = subject_refs.setdefault(
                triple.subject, {"gvp": [], "loc": [], "pref": [], "alt": []}
            )
            refs[bucket].append(triple.obj)

    return term_literal, subject_refs


def build_scope_notes_index(
    path: Path,
) -> tuple[dict[str, tuple[str, str | None]], dict[str, list[str]]]:
    """
    Single pass over `*_ScopeNotes.nt` building:
    - note_text: scopeNote-node URI -> (text, lang)
    - subject_notes: concept URI -> [scopeNote-node URI, ...]
    """

    note_text: dict[str, tuple[str, str | None]] = {}
    subject_notes: dict[str, list[str]] = {}

    for triple in iter_triples(path):
        if triple.predicate == RDF_VALUE and triple.is_literal:
            note_text[triple.subject] = (triple.obj, triple.lang)
            continue

        if triple.predicate == PRED_SCOPE_NOTE and not triple.is_literal:
            subject_notes.setdefault(triple.subject, []).append(triple.obj)

    return note_text, subject_notes


# Bookkeeping predicates used by the (redundant) reified statements found in
# both `*_HierarchicalRels.nt` and `*_AssociativeRels.nt`. Verified by direct
# sampling: every reified rel resource duplicates a *_direct_* triple already
# present on the real concept subject (the reification only adds extra
# metadata like estStart/estEnd/historicFlag, which reconciliation doesn't
# need) - so these bookkeeping triples must be skipped when scanning for
# concept-to-concept edges, both because they'd be redundant and because
# their "subject" is the synthetic rel-node URI, not a real concept.
_REIFICATION_PREDICATES = frozenset(
    {RDF_TYPE_PREDICATE, RDF_SUBJECT, RDF_OBJECT, RDF_PREDICATE}
)


def build_broader_map(path: Path) -> dict[str, list[str]]:
    """
    `*_HierarchicalRels.nt` encodes `gvp:broaderPreferred` (and
    `broaderGeneric`/`broaderNonPreferred`/`broaderPartitive`/
    `broaderInstantial`) as DIRECT triples on the real concept subjects.
    Only `gvp:broaderPreferred` is kept for the reconciliation `broader[]`
    field (matches the single parent shown in `parentString`). A smaller set
    of reified statements duplicating some of these same edges (verified:
    always a subset) is ignored via `_REIFICATION_PREDICATES`.
    """

    broader: dict[str, list[str]] = {}

    for triple in iter_triples(path):
        if triple.is_literal or triple.predicate != PRED_BROADER_PREFERRED:
            continue

        broader.setdefault(triple.subject, []).append(triple.obj)

    return broader


def build_related_map(path: Path) -> dict[str, list[str]]:
    """
    `*_AssociativeRels.nt` encodes many different named relations
    (`gvp:aatNNNN_...`) as DIRECT triples on the real concept subjects, all
    representing a "related concept" edge for reconciliation purposes - the
    specific relation name is not kept. A smaller set of reified statements
    duplicating some of these same edges is ignored via
    `_REIFICATION_PREDICATES`.
    """

    related: dict[str, list[str]] = {}

    for triple in iter_triples(path):
        if triple.is_literal or triple.predicate in _REIFICATION_PREDICATES:
            continue

        related.setdefault(triple.subject, []).append(triple.obj)

    return related


def build_notation_map(path: Path) -> dict[str, str]:
    notation: dict[str, str] = {}

    for triple in iter_triples(path):
        if triple.is_literal:
            notation[triple.subject] = triple.obj

    return notation


def build_exact_match_map(path: Path) -> dict[str, list[str]]:
    exact_match: dict[str, list[str]] = {}

    for triple in iter_triples(path):
        if not triple.is_literal:
            exact_match.setdefault(triple.subject, []).append(triple.obj)

    return exact_match


def build_lookups(raw_dir: Path, vocab: GettyVocabSpec) -> GettyLookups:
    term_literal, subject_term_refs = build_terms_index(
        vocab_file(raw_dir, vocab, FILE_TERMS)
    )
    scope_note_text, subject_scope_notes = build_scope_notes_index(
        vocab_file(raw_dir, vocab, FILE_SCOPE_NOTES)
    )
    broader = build_broader_map(vocab_file(raw_dir, vocab, FILE_HIERARCHICAL_RELS))
    related = build_related_map(vocab_file(raw_dir, vocab, FILE_ASSOCIATIVE_RELS))
    notation = build_notation_map(vocab_file(raw_dir, vocab, FILE_NOTATIONS))
    exact_match = build_exact_match_map(vocab_file(raw_dir, vocab, FILE_LCSH_ALIGNMENT))

    return GettyLookups(
        term_literal=term_literal,
        subject_term_refs=subject_term_refs,
        scope_note_text=scope_note_text,
        subject_scope_notes=subject_scope_notes,
        broader=broader,
        related=related,
        notation=notation,
        exact_match=exact_match,
    )


def pick_term(
    term_ids: list[str],
    term_literal: dict[str, tuple[str, str | None]],
    prefer_lang: str = "en",
) -> tuple[str, str, str | None] | None:
    """
    Returns (term_id, text, lang) for the first term matching `prefer_lang`,
    or the first term with any usable literal otherwise.
    """

    fallback: tuple[str, str, str | None] | None = None

    for term_id in term_ids:
        literal = term_literal.get(term_id)

        if literal is None:
            continue

        text, lang = literal

        if fallback is None:
            fallback = (term_id, text, lang)

        if lang == prefer_lang:
            return (term_id, text, lang)

    return fallback


def resolve_preferred_and_variant_names(
    subject_uri: str,
    lookups: GettyLookups,
    prefer_lang: str = "en",
) -> tuple[str | None, list[str]]:
    """
    Picks a preferredName (prefer the official gvp:prefLabelGVP term; if its
    language isn't English, prefer an English skos-xl:prefLabel term
    instead) and a deduplicated variantName[] from all other term
    literalForms.
    """

    refs = lookups.subject_term_refs.get(
        subject_uri, {"gvp": [], "loc": [], "pref": [], "alt": []}
    )
    gvp_ids = refs.get("gvp", [])
    loc_ids = refs.get("loc", [])
    pref_ids = refs.get("pref", [])
    alt_ids = refs.get("alt", [])

    preferred_term = pick_term(gvp_ids, lookups.term_literal, prefer_lang)

    if preferred_term is None or preferred_term[2] != prefer_lang:
        english_pref = pick_term(pref_ids, lookups.term_literal, prefer_lang)

        if english_pref is not None and english_pref[2] == prefer_lang:
            preferred_term = english_pref

    if preferred_term is None:
        preferred_term = pick_term(pref_ids, lookups.term_literal, prefer_lang)

    if preferred_term is None:
        preferred_term = pick_term(loc_ids, lookups.term_literal, prefer_lang)

    if preferred_term is None:
        preferred_term = pick_term(alt_ids, lookups.term_literal, prefer_lang)

    preferred_name = preferred_term[1] if preferred_term else None
    preferred_term_id = preferred_term[0] if preferred_term else None

    all_term_ids: list[str] = []
    seen_ids: set[str] = set()

    for term_id in (*gvp_ids, *loc_ids, *pref_ids, *alt_ids):
        if term_id not in seen_ids:
            seen_ids.add(term_id)
            all_term_ids.append(term_id)

    variant_names: list[str] = []
    seen_texts: set[str] = set()

    if preferred_name:
        seen_texts.add(preferred_name)

    for term_id in all_term_ids:
        if term_id == preferred_term_id:
            continue

        literal = lookups.term_literal.get(term_id)

        if literal is None:
            continue

        text, _lang = literal

        if text in seen_texts:
            continue

        seen_texts.add(text)
        variant_names.append(text)

    return preferred_name, variant_names


def resolve_scope_note(
    subject_uri: str,
    lookups: GettyLookups,
    prefer_lang: str = "en",
) -> str | None:
    note_ids = lookups.subject_scope_notes.get(subject_uri, [])
    fallback: str | None = None

    for note_id in note_ids:
        note = lookups.scope_note_text.get(note_id)

        if note is None:
            continue

        text, lang = note

        if fallback is None:
            fallback = text

        if lang == prefer_lang:
            return text

    return fallback


def uri_to_subject_id(uri: str) -> str:
    return uri.rstrip("/").rsplit("/", 1)[-1]


def normalize_subject(
    subject_uri: str,
    triples: list[Triple],
    vocab: GettyVocabSpec,
    lookups: GettyLookups,
) -> dict[str, Any] | None:
    """
    Normalizes one AAT (or future ULAN/TGN) concept subject from
    `*_1Subjects.nt` into the shared reconciliation document contract.
    Returns None if no usable preferredName could be resolved (mirrors GND's
    `normalize_gnd_lds_record` skipping records without a preferred name).
    """

    type_key = vocab.default_type_key
    parent_string: str | None = None
    parent_string_abbrev: str | None = None
    subject_id: str | None = None

    for triple in triples:
        if triple.predicate == RDF_TYPE_PREDICATE and not triple.is_literal:
            type_key = local_name(triple.obj)
        elif triple.predicate == PRED_PARENT_STRING and triple.is_literal:
            parent_string = triple.obj
        elif triple.predicate == PRED_PARENT_STRING_ABBREV and triple.is_literal:
            parent_string_abbrev = triple.obj
        elif triple.predicate == PRED_IDENTIFIER and triple.is_literal:
            subject_id = triple.obj

    if subject_id is None:
        subject_id = uri_to_subject_id(subject_uri)

    preferred_name, variant_names = resolve_preferred_and_variant_names(
        subject_uri, lookups
    )

    if not preferred_name:
        return None

    scope_note = resolve_scope_note(subject_uri, lookups)
    broader_uris = lookups.broader.get(subject_uri, [])
    related_uris = lookups.related.get(subject_uri, [])
    notation = lookups.notation.get(subject_uri)
    exact_match = lookups.exact_match.get(subject_uri, [])

    literal_fields = {
        "parentString": parent_string,
        "parentStringAbbrev": parent_string_abbrev,
        "scopeNote": scope_note,
        "notation": notation,
    }

    available_properties = [name for name, value in literal_fields.items() if value]

    if broader_uris:
        available_properties.append("broader")

    if related_uris:
        available_properties.append("related")

    if exact_match:
        available_properties.append("exactMatch")

    properties_flat = [
        {"id": name, "value": value} for name, value in literal_fields.items() if value
    ]

    return {
        "id": f"{vocab.key}/{subject_id}",
        "subjectId": subject_id,
        "vocabulary": vocab.key,
        "uri": subject_uri,
        "source": f"getty-{vocab.key}-explicit",
        "preferredName": preferred_name,
        "variantName": variant_names,
        "type": [type_key],
        "parentString": parent_string,
        "parentStringAbbrev": parent_string_abbrev,
        "scopeNote": scope_note,
        "broader": [f"{vocab.key}/{uri_to_subject_id(uri)}" for uri in broader_uris],
        "related": [f"{vocab.key}/{uri_to_subject_id(uri)}" for uri in related_uris],
        "notation": notation,
        "exactMatch": exact_match,
        "availableProperties": available_properties,
        "propertiesFlat": properties_flat,
    }


def normalize_obsolete_subject(
    subject_uri: str,
    triples: list[Triple],
    vocab: GettyVocabSpec,
) -> dict[str, Any] | None:
    """
    `*_ObsoleteSubjects.nt` has a simpler, self-contained shape: a plain
    `skos:prefLabel` literal (no SKOS-XL indirection), no parentString/
    scopeNote/notation/broader/related.
    """

    preferred_name: str | None = None
    subject_id: str | None = None

    for triple in triples:
        if triple.predicate == PRED_PREF_LABEL_PLAIN and triple.is_literal:
            preferred_name = triple.obj
        elif triple.predicate == PRED_IDENTIFIER and triple.is_literal:
            subject_id = triple.obj

    if not preferred_name:
        return None

    if subject_id is None:
        subject_id = uri_to_subject_id(subject_uri)

    return {
        "id": f"{vocab.key}/{subject_id}",
        "subjectId": subject_id,
        "vocabulary": vocab.key,
        "uri": subject_uri,
        "source": f"getty-{vocab.key}-explicit",
        "preferredName": preferred_name,
        "variantName": [],
        "type": ["ObsoleteSubject"],
        "parentString": None,
        "parentStringAbbrev": None,
        "scopeNote": None,
        "broader": [],
        "related": [],
        "notation": None,
        "exactMatch": [],
        "availableProperties": [],
        "propertiesFlat": [],
    }


def iter_normalized_getty_records(
    raw_dir: Path,
    vocab_key: str,
    limit: int | None = None,
) -> Iterator[dict[str, Any]]:
    """
    Streams normalized reconciliation documents for one Getty vocabulary:
    all current (non-obsolete) subjects first, then obsolete subjects (if
    the corresponding file was extracted).
    """

    vocab = get_vocab_spec(vocab_key)
    lookups = build_lookups(raw_dir, vocab)

    yielded = 0

    subjects_path = vocab_file(raw_dir, vocab, FILE_SUBJECTS)

    for subject_uri, triples in iter_subject_groups(subjects_path):
        normalized = normalize_subject(subject_uri, triples, vocab, lookups)

        if normalized is None:
            continue

        yield normalized
        yielded += 1

        if limit is not None and yielded >= limit:
            return

    obsolete_path = vocab_file(raw_dir, vocab, FILE_OBSOLETE_SUBJECTS)

    if obsolete_path.exists():
        for subject_uri, triples in iter_subject_groups(obsolete_path):
            normalized = normalize_obsolete_subject(subject_uri, triples, vocab)

            if normalized is None:
                continue

            yield normalized
            yielded += 1

            if limit is not None and yielded >= limit:
                return


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize a Getty vocabulary explicit export (dry-run / inspection)."
    )

    parser.add_argument(
        "--vocab",
        default="aat",
        choices=sorted(GETTY_VOCAB_SPECS.keys()),
        help="Getty vocabulary key. Default: aat",
    )

    parser.add_argument(
        "--raw-dir",
        default=str(GETTY_RAW_DIR),
        help=f"Directory containing extracted Getty .nt files. Default: {GETTY_RAW_DIR}",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Stop after normalizing N records.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print normalized documents as JSON instead of just counting them.",
    )

    args = parser.parse_args()

    raw_dir = Path(args.raw_dir)
    count = 0

    for record in iter_normalized_getty_records(
        raw_dir=raw_dir,
        vocab_key=args.vocab,
        limit=args.limit,
    ):
        count += 1

        if args.dry_run:
            print(json.dumps(record, ensure_ascii=False, indent=2))

    print(f"[NORMALIZE] vocab={args.vocab} records={count:,}", file=sys.stderr)


if __name__ == "__main__":
    main()
