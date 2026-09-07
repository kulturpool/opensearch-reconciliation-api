"""
Fixture-based tests for importer/normalize_getty.py's two-pass normalizer.

tests/fixtures/getty_aat/aat/ contains a small, hand-written explicit-export
fixture (2 current concepts + 1 obsolete subject) covering: SKOS-XL
preferred/variant term resolution, scopeNote join, broaderPreferred,
associative relations, notation, and exactMatch - i.e. every join lookups
in importer/normalize_getty.py's GettyLookups.
"""

from pathlib import Path

from importer.normalize_getty import (
    iter_normalized_getty_records,
    normalize_obsolete_subject,
    normalize_subject,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "getty_aat"


def test_iter_normalized_getty_records_yields_current_then_obsolete():
    records = list(iter_normalized_getty_records(FIXTURES_DIR, "aat"))

    assert [record["subjectId"] for record in records] == [
        "300007466",
        "300264092",
        "300007467",
    ]


def test_current_subject_full_shape():
    records = {
        record["subjectId"]: record
        for record in iter_normalized_getty_records(FIXTURES_DIR, "aat")
    }
    painting = records["300007466"]

    assert painting["id"] == "aat/300007466"
    assert painting["vocabulary"] == "aat"
    assert painting["uri"] == "http://vocab.getty.edu/aat/300007466"
    assert painting["source"] == "getty-aat-explicit"
    assert painting["type"] == ["Concept"]

    # Preferred name comes from the English gvp:prefLabelGVP term.
    assert painting["preferredName"] == "Painting"
    # Variant name comes from the skos-xl:altLabel term, deduplicated
    # against the preferred name.
    assert painting["variantName"] == ["Painting (visual works)"]

    assert painting["parentString"] == (
        "Painting (image-making) (<visual works by medium or technique>, ..., Objects Facet)"
    )
    assert painting["parentStringAbbrev"] == "... Objects Facet"
    assert painting["scopeNote"] == (
        "Refers to the activity of creating a two-dimensional image using pigments."
    )
    assert painting["notation"] == "AAT-300007466"
    assert painting["exactMatch"] == ["http://id.loc.gov/authorities/subjects/sh85097633"]
    assert painting["broader"] == ["aat/300264092"]
    assert painting["related"] == ["aat/300069207"]

    assert sorted(painting["availableProperties"]) == sorted(
        [
            "parentString",
            "parentStringAbbrev",
            "scopeNote",
            "notation",
            "broader",
            "related",
            "exactMatch",
        ]
    )
    assert {"id": "parentString", "value": painting["parentString"]} in painting[
        "propertiesFlat"
    ]
    assert {"id": "notation", "value": "AAT-300007466"} in painting["propertiesFlat"]


def test_subject_without_optional_fields_has_minimal_shape():
    records = {
        record["subjectId"]: record
        for record in iter_normalized_getty_records(FIXTURES_DIR, "aat")
    }
    styles_and_periods = records["300264092"]

    assert styles_and_periods["preferredName"] == "Styles and Periods (Hierarchy Name)"
    assert styles_and_periods["variantName"] == []
    assert styles_and_periods["parentString"] is None
    assert styles_and_periods["scopeNote"] is None
    assert styles_and_periods["notation"] is None
    assert styles_and_periods["broader"] == []
    assert styles_and_periods["related"] == []
    assert styles_and_periods["exactMatch"] == []
    assert styles_and_periods["availableProperties"] == []
    assert styles_and_periods["propertiesFlat"] == []


def test_obsolete_subject_has_simplified_shape():
    records = {
        record["subjectId"]: record
        for record in iter_normalized_getty_records(FIXTURES_DIR, "aat")
    }
    obsolete = records["300007467"]

    assert obsolete["id"] == "aat/300007467"
    assert obsolete["vocabulary"] == "aat"
    assert obsolete["preferredName"] == "old term (obsolete)"
    assert obsolete["type"] == ["ObsoleteSubject"]
    assert obsolete["variantName"] == []
    assert obsolete["broader"] == []
    assert obsolete["related"] == []
    assert obsolete["availableProperties"] == []


def test_limit_stops_after_n_current_subjects():
    records = list(iter_normalized_getty_records(FIXTURES_DIR, "aat", limit=1))

    assert len(records) == 1
    assert records[0]["subjectId"] == "300007466"


def test_normalize_subject_returns_none_without_preferred_name():
    from importer.getty_vocab_specs import AAT_SPEC
    from importer.normalize_getty import GettyLookups

    empty_lookups = GettyLookups(
        term_literal={},
        subject_term_refs={},
        scope_note_text={},
        subject_scope_notes={},
        broader={},
        related={},
        notation={},
        exact_match={},
    )

    result = normalize_subject(
        "http://vocab.getty.edu/aat/999999999",
        triples=[],
        vocab=AAT_SPEC,
        lookups=empty_lookups,
    )

    assert result is None


def test_normalize_obsolete_subject_returns_none_without_pref_label():
    from importer.getty_vocab_specs import AAT_SPEC

    result = normalize_obsolete_subject(
        "http://vocab.getty.edu/aat/999999999",
        triples=[],
        vocab=AAT_SPEC,
    )

    assert result is None
