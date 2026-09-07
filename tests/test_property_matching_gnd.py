"""
Characterization tests for api/services/property_matching.py.
"""

from api.services.property_matching import (
    calculate_mismatch_penalty,
    calculate_property_bonus,
    get_property_aliases,
    score_property_match,
)


class TestScorePropertyMatch:
    def test_exact_identifier_match_scores_10(self):
        result = score_property_match(
            expected_values=["https://d-nb.info/gnd/118540238"],
            actual_values=["118540238"],
        )
        assert result == {"matched": True, "score": 10}

    def test_identical_raw_string_scores_10_via_identifier_shortcut(self):
        # compact_identifier() is the identity function for non-URI strings,
        # so byte-identical values take the "exact identifier match" branch
        # (score 10) rather than the "exact normalized literal" branch.
        result = score_property_match(
            expected_values=["Frankfurt am Main"],
            actual_values=["Frankfurt am Main"],
        )
        assert result == {"matched": True, "score": 10}

    def test_exact_normalized_literal_match_scores_8(self):
        # Differs in case/whitespace, so it misses the raw-identity shortcut
        # but is still equal after normalize_text().
        result = score_property_match(
            expected_values=["frankfurt   am main"],
            actual_values=["Frankfurt AM Main"],
        )
        assert result == {"matched": True, "score": 8}

    def test_shared_year_date_aware_match_scores_7(self):
        result = score_property_match(
            expected_values=["1749"],
            actual_values=["1749-08-28"],
        )
        assert result == {"matched": True, "score": 7}

    def test_containment_match_scores_5(self):
        result = score_property_match(
            expected_values=["Frankfurt"],
            actual_values=["Frankfurt am Main"],
        )
        assert result == {"matched": True, "score": 5}

    def test_no_overlap_does_not_match(self):
        result = score_property_match(
            expected_values=["Berlin"],
            actual_values=["Frankfurt am Main"],
        )
        assert result["matched"] is False
        assert result["score"] == 0

    def test_empty_values_do_not_match(self):
        assert score_property_match([], ["x"]) == {"matched": False, "score": 0}
        assert score_property_match(["x"], []) == {"matched": False, "score": 0}


class TestCalculateMismatchPenalty:
    def test_date_field_gets_high_penalty(self):
        assert calculate_mismatch_penalty("dateOfEstablishment", match_score=0) == 6

    def test_place_field_gets_medium_penalty(self):
        assert calculate_mismatch_penalty("placeOfBirth", match_score=0) == 4

    def test_generic_field_gets_low_penalty(self):
        assert calculate_mismatch_penalty("someOtherProperty", match_score=0) == 2


class TestGetPropertyAliases:
    def test_preferred_name_expands_to_type_specific_aliases(self):
        aliases = get_property_aliases("preferredName")
        assert "preferredName" in aliases
        assert "preferredNameForThePerson" in aliases

    def test_unknown_property_id_returns_itself(self):
        assert get_property_aliases("someCustomProperty") == ["someCustomProperty"]


class TestCalculatePropertyBonus:
    def test_no_requested_properties_returns_zero(self, goethe_record):
        bonus, penalty, features = calculate_property_bonus(goethe_record, [])
        assert (bonus, penalty, features) == (0, 0, [])

    def test_matching_property_adds_bonus(self, goethe_record):
        bonus, penalty, features = calculate_property_bonus(
            goethe_record,
            requested_properties=[
                {"pid": "placeOfBirth", "v": "Frankfurt am Main"},
            ],
        )
        assert bonus > 0
        assert penalty == 0

    def test_mismatching_property_on_present_field_adds_penalty(self, goethe_record):
        bonus, penalty, features = calculate_property_bonus(
            goethe_record,
            requested_properties=[
                {"pid": "placeOfBirth", "v": "Berlin"},
            ],
        )
        assert bonus == 0
        assert penalty > 0

    def test_missing_field_on_candidate_gives_no_penalty(self, goethe_record):
        bonus, penalty, features = calculate_property_bonus(
            goethe_record,
            requested_properties=[
                {"pid": "dateOfEstablishment", "v": "1900"},
            ],
        )
        assert bonus == 0
        assert penalty == 0

    def test_bonus_is_capped_at_max_bonus(self, goethe_record):
        bonus, penalty, features = calculate_property_bonus(
            goethe_record,
            requested_properties=[
                {"pid": "placeOfBirth", "v": "Frankfurt am Main"},
                {"pid": "placeOfDeath", "v": "Weimar"},
                {"pid": "professionOrOccupation", "v": "Schriftsteller"},
            ],
            max_bonus=5,
        )
        assert bonus == 5
