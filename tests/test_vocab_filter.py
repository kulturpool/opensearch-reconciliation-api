"""
Tests for vocabulary-scoped type filtering in api/services/search.py.

Covers:
- each vocab's msearch/search calls target its own OpenSearch index
  (never cross-contaminating "gnd" and "getty").
- root-type requests (vocab.root_type["id"], e.g. GND's "AuthorityResource"
  or Getty's "aat") never turn into a `type` terms filter/match-check, since
  every candidate implicitly has that type (see format_entity_types()).
  Regression test for a bug where this check was hardcoded to the literal
  string "AuthorityResource", which meant requesting Getty's root type
  ("aat") incorrectly added a `{"terms": {"type": ["aat"]}}` filter that no
  Getty document could ever match.
"""

from api.services.search import (
    build_search_body,
    candidate_matches_requested_type,
    is_root_type,
)
from api.vocabularies.getty import AAT_VOCAB
from api.vocabularies.gnd import GND_VOCAB


class TestIsRootType:
    def test_gnd_authority_resource_is_root_type(self):
        assert is_root_type("AuthorityResource", vocab=GND_VOCAB) is True

    def test_gnd_concrete_type_is_not_root_type(self):
        assert is_root_type("DifferentiatedPerson", vocab=GND_VOCAB) is False

    def test_getty_aat_is_root_type(self):
        assert is_root_type("aat", vocab=AAT_VOCAB) is True

    def test_getty_concrete_type_is_not_root_type(self):
        assert is_root_type("aat:Concept", vocab=AAT_VOCAB) is False

    def test_none_entity_type_is_not_root_type(self):
        assert is_root_type(None, vocab=GND_VOCAB) is False
        assert is_root_type(None, vocab=AAT_VOCAB) is False


class TestBuildSearchBodyIndexScoping:
    def test_gnd_query_targets_gnd_index(self):
        body = build_search_body(query="Goethe", limit=5, vocab=GND_VOCAB)
        assert body["_source"]["includes"] == list(GND_VOCAB.source_fields)

    def test_getty_query_targets_getty_source_fields(self):
        body = build_search_body(query="painting", limit=5, vocab=AAT_VOCAB)
        assert body["_source"]["includes"] == list(AAT_VOCAB.source_fields)
        # GND-only fields must never leak into a Getty query.
        assert "dateOfBirth" not in body["_source"]["includes"]


class TestRootTypeIsNeverFiltered:
    def test_gnd_root_type_produces_no_filter(self):
        body = build_search_body(
            query="Goethe", limit=5, entity_type="AuthorityResource", vocab=GND_VOCAB
        )
        assert body["query"]["bool"]["filter"] == []

    def test_getty_root_type_produces_no_filter(self):
        body = build_search_body(
            query="painting", limit=5, entity_type="aat", vocab=AAT_VOCAB
        )
        assert body["query"]["bool"]["filter"] == [{"term": {"vocabulary": "aat"}}]

    def test_getty_concrete_type_produces_a_filter(self):
        body = build_search_body(
            query="painting", limit=5, entity_type="aat:Concept", vocab=AAT_VOCAB
        )
        assert body["query"]["bool"]["filter"]
        terms_filter = body["query"]["bool"]["filter"][1]["terms"]["type"]
        assert list(terms_filter) == ["aat:Concept"]


class TestCandidateMatchesRequestedType:
    def test_gnd_root_type_matches_any_candidate(self):
        source = {"type": ["DifferentiatedPerson"]}
        assert candidate_matches_requested_type(
            source, "AuthorityResource", vocab=GND_VOCAB
        )

    def test_getty_root_type_matches_any_candidate(self):
        source = {"type": ["aat:Concept"]}
        assert candidate_matches_requested_type(source, "aat", vocab=AAT_VOCAB)

    def test_getty_concrete_type_requires_matching_candidate_type(self):
        source = {"type": ["aat:Concept"]}
        assert candidate_matches_requested_type(source, "aat:Concept", vocab=AAT_VOCAB)
        assert not candidate_matches_requested_type(
            source, "aat:Facet", vocab=AAT_VOCAB
        )
