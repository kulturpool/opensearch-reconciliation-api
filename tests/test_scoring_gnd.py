"""
Characterization tests for api/services/search.py scoring pipeline.

These pin CURRENT behaviour (post .lowercase-bugfix, see
/memories/repo/local_reconciliation_api.md) before the VocabConfig refactor,
so any accidental behaviour change during the refactor is caught.
"""

from api.services.search import (
    apply_match_decision,
    max_property_bonus_for_base_score,
    normalize_score,
    score_date_signals,
)


class TestNormalizeScore:
    def test_exact_identifier_match_scores_100(self, goethe_record):
        score, signals = normalize_score(
            raw_score=5.0,
            query="118540238",
            source=goethe_record,
        )
        assert score == 100

    def test_exact_preferred_name_match_scores_96(self, goethe_record):
        score, signals = normalize_score(
            raw_score=5.0,
            query="Goethe, Johann Wolfgang von",
            source=goethe_record,
        )
        assert score == 96
        assert signals["exact_name_match"] is True

    def test_natural_order_name_matches_inverted_preferred_name(self, goethe_record):
        # "Johann Wolfgang von Goethe" (natural order) should be recognized as
        # equivalent to the inverted GND-style "Goethe, Johann Wolfgang von".
        score, signals = normalize_score(
            raw_score=5.0,
            query="Johann Wolfgang von Goethe",
            source=goethe_record,
        )
        assert score == 96
        assert signals["exact_name_match"] is True

    def test_exact_variant_name_match_scores_92(self, goethe_record):
        score, signals = normalize_score(
            raw_score=5.0,
            query="Goethe, Johann W.",
            source=goethe_record,
        )
        assert score == 92
        assert signals["exact_name_match"] is True

    def test_fuzzy_typo_tolerant_match(self, goethe_record):
        score, signals = normalize_score(
            raw_score=5.0,
            query="Goethe, Johann Wolfgan von",  # missing a "g"
            source=goethe_record,
        )
        assert 80 <= score < 96
        assert signals["exact_name_match"] is False

    def test_unrelated_query_falls_back_to_raw_score(self, goethe_record):
        score, signals = normalize_score(
            raw_score=1.0,
            query="Totally Unrelated Query Text",
            source=goethe_record,
        )
        assert score < 60
        assert signals["exact_name_match"] is False

    def test_matching_birth_year_property_boosts_score(self, goethe_record):
        score_without, _ = normalize_score(
            raw_score=5.0,
            query="Goethe, Johann Wolfgang von",
            source=goethe_record,
        )
        score_with, signals_with = normalize_score(
            raw_score=5.0,
            query="Goethe, Johann Wolfgang von",
            source=goethe_record,
            requested_properties=[{"pid": "dateOfBirth", "v": "1749"}],
        )
        assert signals_with["birth_match"] is True
        assert score_with >= score_without

    def test_mismatched_birth_year_penalizes_score(self, goethe_record):
        score_without, _ = normalize_score(
            raw_score=5.0,
            query="Goethe, Johann Wolfgang von",
            source=goethe_record,
        )
        score_with, signals_with = normalize_score(
            raw_score=5.0,
            query="Goethe, Johann Wolfgang von",
            source=goethe_record,
            requested_properties=[{"pid": "dateOfBirth", "v": "1900"}],
        )
        assert signals_with["birth_match"] is False
        assert score_with <= score_without

    def test_type_match_gives_small_bonus(self, goethe_record):
        score_without, _ = normalize_score(
            raw_score=5.0,
            query="Goethe, Johann Wolfgang von",
            source=goethe_record,
        )
        score_with, signals_with = normalize_score(
            raw_score=5.0,
            query="Goethe, Johann Wolfgang von",
            source=goethe_record,
            requested_type="DifferentiatedPerson",
        )
        assert signals_with["type_match"] is True
        assert score_with >= score_without

    def test_score_never_exceeds_100(self, goethe_record):
        score, _ = normalize_score(
            raw_score=5.0,
            query="Goethe, Johann Wolfgang von",
            source=goethe_record,
            requested_type="DifferentiatedPerson",
            requested_properties=[
                {"pid": "dateOfBirth", "v": "1749"},
                {"pid": "dateOfDeath", "v": "1832"},
                {"pid": "placeOfBirth", "v": "Frankfurt am Main"},
            ],
        )
        assert score <= 100


class TestMaxPropertyBonusForBaseScore:
    def test_exact_match_gets_full_headroom(self):
        assert max_property_bonus_for_base_score(96) == 20

    def test_strong_fuzzy_gets_moderate_headroom(self):
        assert max_property_bonus_for_base_score(85) == 12

    def test_weak_fallback_gets_minimal_headroom(self):
        assert max_property_bonus_for_base_score(0) == 1


class TestScoreDateSignals:
    def test_no_requested_dates_returns_zero(self, goethe_record):
        result = score_date_signals(goethe_record, requested_properties=[])
        assert result == {
            "bonus": 0,
            "penalty": 0,
            "birth_match": False,
            "death_match": False,
        }

    def test_exact_birth_and_death_year_both_match(self, goethe_record):
        result = score_date_signals(
            goethe_record,
            requested_properties=[
                {"pid": "dateOfBirth", "v": "1749"},
                {"pid": "dateOfDeath", "v": "1832"},
            ],
        )
        assert result["birth_match"] is True
        assert result["death_match"] is True
        # 14 (birth) + 14 (death) + 10 (both-match bonus)
        assert result["bonus"] == 38
        assert result["penalty"] == 0

    def test_off_by_one_year_gets_small_bonus_not_penalty(self, goethe_record):
        result = score_date_signals(
            goethe_record,
            requested_properties=[{"pid": "dateOfBirth", "v": "1750"}],
        )
        assert result["birth_match"] is False
        assert result["bonus"] == 4
        assert result["penalty"] == 0

    def test_clearly_wrong_year_is_penalized(self, goethe_record):
        result = score_date_signals(
            goethe_record,
            requested_properties=[{"pid": "dateOfBirth", "v": "1900"}],
        )
        assert result["birth_match"] is False
        assert result["bonus"] == 0
        assert result["penalty"] == 6


class TestApplyMatchDecision:
    def test_single_clear_winner_is_marked_as_match(self, goethe_record):
        results = [
            {
                "id": "118540238",
                "score": 96,
                "_signals": {
                    "exact_name_match": True,
                    "type_match": False,
                    "birth_match": False,
                    "death_match": False,
                },
            }
        ]
        apply_match_decision(results, requested_properties=[])
        assert results[0]["match"] is True

    def test_ambiguous_tie_is_not_matched(self):
        # Two equally-strong exact name matches (e.g. two different people
        # with the same name) - must not auto-match. apply_match_decision()
        # never sets match=False explicitly, it just leaves the key absent.
        results = [
            {
                "id": "A",
                "score": 96,
                "_signals": {"exact_name_match": True, "type_match": False,
                              "birth_match": False, "death_match": False},
            },
            {
                "id": "B",
                "score": 96,
                "_signals": {"exact_name_match": True, "type_match": False,
                              "birth_match": False, "death_match": False},
            },
        ]
        apply_match_decision(results, requested_properties=[])
        assert "match" not in results[0]

    def test_weak_top_score_without_corroboration_is_not_matched(self):
        results = [
            {
                "id": "A",
                "score": 60,
                "_signals": {"exact_name_match": False, "type_match": False,
                              "birth_match": False, "death_match": False},
            },
        ]
        apply_match_decision(results, requested_properties=[])
        assert "match" not in results[0]

    def test_small_gap_below_required_threshold_is_not_matched(self):
        results = [
            {
                "id": "A",
                "score": 91,
                "_signals": {"exact_name_match": True, "type_match": False,
                              "birth_match": False, "death_match": False},
            },
            {
                "id": "B",
                "score": 89,
                "_signals": {"exact_name_match": False, "type_match": False,
                              "birth_match": False, "death_match": False},
            },
        ]
        # gap = 2, required_gap for score>=90 with no requested properties is 6
        apply_match_decision(results, requested_properties=[])
        assert "match" not in results[0]
