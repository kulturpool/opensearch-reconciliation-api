"""
Fixture-based tests for the ULAN/TGN-specific fields added to
importer/normalize_getty.py: nationality, role, biography (ULAN),
coordinates and placeType (TGN).

tests/fixtures/getty_ulan/ulan/ and tests/fixtures/getty_tgn/tgn/ each
contain two subjects: one with the new fields populated, one without
(to confirm the fields default to empty/None and are omitted from
availableProperties when absent).
"""

from pathlib import Path

from importer.normalize_getty import iter_normalized_getty_records

ULAN_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "getty_ulan"
TGN_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "getty_tgn"


def test_ulan_subject_has_nationality_role_and_biography():
    records = {
        record["subjectId"]: record
        for record in iter_normalized_getty_records(ULAN_FIXTURES_DIR, "ulan")
    }
    rembrandt = records["500000001"]

    assert rembrandt["preferredName"] == "Rembrandt van Rijn"
    # nationalityPreferred/nationalityNonPreferred both resolve to composite
    # AAT refs via the "-agent" subject-URI convention.
    assert rembrandt["nationality"] == ["aat/300111159", "aat/300111178"]
    # agentTypePreferred (Roles) uses the plain subject URI, no "-agent" suffix.
    assert rembrandt["role"] == ["aat/300025103"]
    # biographyPreferred resolves through the "-agent" subject to a bio node,
    # then to its schema:description literal.
    assert rembrandt["biography"] == [
        "Dutch painter; born Leiden, 1606; died Amsterdam, 1669"
    ]
    assert rembrandt["placeType"] == []
    assert rembrandt["coordinates"] is None

    assert sorted(rembrandt["availableProperties"]) == sorted(
        ["parentStringAbbrev", "nationality", "role", "biography"]
    )


def test_ulan_subject_without_new_fields_has_empty_defaults():
    records = {
        record["subjectId"]: record
        for record in iter_normalized_getty_records(ULAN_FIXTURES_DIR, "ulan")
    }
    jane_doe = records["500000002"]

    assert jane_doe["nationality"] == []
    assert jane_doe["role"] == []
    assert jane_doe["biography"] == []
    assert jane_doe["placeType"] == []
    assert jane_doe["coordinates"] is None
    assert jane_doe["availableProperties"] == []


def test_tgn_subject_has_coordinates_and_place_type():
    records = {
        record["subjectId"]: record
        for record in iter_normalized_getty_records(TGN_FIXTURES_DIR, "tgn")
    }
    amsterdam = records["7000001"]

    assert amsterdam["preferredName"] == "Amsterdam"
    # geo:lat/geo:long joined via the "-place" subject-URI convention.
    assert amsterdam["coordinates"] == "52.37, 4.895"
    # placeTypePreferred resolves to a composite AAT ref via the plain
    # subject URI (no suffix).
    assert amsterdam["placeType"] == ["aat/300008389"]
    assert amsterdam["nationality"] == []
    assert amsterdam["role"] == []
    assert amsterdam["biography"] == []

    assert sorted(amsterdam["availableProperties"]) == sorted(
        ["coordinates", "placeType"]
    )
    assert {"id": "coordinates", "value": "52.37, 4.895"} in amsterdam[
        "propertiesFlat"
    ]


def test_tgn_subject_without_new_fields_has_empty_defaults():
    records = {
        record["subjectId"]: record
        for record in iter_normalized_getty_records(TGN_FIXTURES_DIR, "tgn")
    }
    rotterdam = records["7000002"]

    assert rotterdam["coordinates"] is None
    assert rotterdam["placeType"] == []
    assert rotterdam["availableProperties"] == []
