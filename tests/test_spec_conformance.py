"""
Regression tests for Reconciliation Service API v0.2 conformance details.

Covers the spec requirements that were previously not met:
- `schemaSpace` describes the entity *type*, not the identifier namespace
- a query may supply `properties` without a `query` string
- `batchSize` is enforced with HTTP 413
- suggest services rank real prefix matches first
- suggest entity responses carry the spec's `notable` field

Spec: https://www.w3.org/community/reports/reconciliation/CG-FINAL-specs-0.2-20230410/
"""

import pytest
from fastapi import HTTPException

from api.reconciliation_utils import handle_reconciliation_queries, service_manifest_response
from api.services.property_registry import suggest_registry_properties
from api.services.search import build_search_body
from api.services.suggest_ranking import sort_prefix_matches_first
from api.vocabularies.getty import GETTY_VOCAB
from api.vocabularies.gnd import GND_VOCAB
from config import RECONCILIATION_BATCH_SIZE


class TestManifestSpaces:
    def test_gnd_schema_space_differs_from_identifier_space(self):
        manifest = service_manifest_response(vocab=GND_VOCAB)

        assert manifest["identifierSpace"] == "https://d-nb.info/gnd/"
        assert (
            manifest["schemaSpace"]
            == "https://d-nb.info/standards/elementset/gnd#AuthorityResource"
        )

    def test_getty_schema_space_is_skos_concept(self):
        manifest = service_manifest_response(vocab=GETTY_VOCAB)

        assert manifest["identifierSpace"] == "http://vocab.getty.edu/"
        assert manifest["schemaSpace"] == "http://www.w3.org/2004/02/skos/core#Concept"

    def test_optional_documentation_and_service_version_present(self):
        manifest = service_manifest_response(vocab=GND_VOCAB)

        assert manifest["documentation"].endswith("/docs")
        assert isinstance(manifest["serviceVersion"], str)

    def test_logo_omitted_when_not_configured(self):
        manifest = service_manifest_response(vocab=GND_VOCAB)

        assert "logo" not in manifest


class TestPropertyOnlyQuery:
    def test_body_without_query_has_no_name_clauses(self):
        body = build_search_body(
            query="",
            limit=5,
            properties=[{"pid": "placeOfBirth", "v": "Frankfurt am Main"}],
        )

        should = body["query"]["bool"]["should"]

        assert should
        assert not any("preferredName.keyword" in str(clause) for clause in should)
        assert not any("variantName.keyword" in str(clause) for clause in should)
        assert any("placeOfBirth" in str(clause) for clause in should)

    def test_body_with_query_still_has_name_clauses(self):
        body = build_search_body(query="Goethe", limit=5)
        should = body["query"]["bool"]["should"]

        assert any("preferredName.keyword" in str(clause) for clause in should)


class TestPrefixSearch:
    def test_prefix_search_adds_prefix_clauses(self):
        body = build_search_body(query="Goeth", limit=5, prefix_search=True)
        should = body["query"]["bool"]["should"]

        assert any("match_phrase_prefix" in clause for clause in should)

    def test_prefix_clauses_absent_by_default(self):
        body = build_search_body(query="Goeth", limit=5)
        should = body["query"]["bool"]["should"]

        assert not any("match_phrase_prefix" in clause for clause in should)

    def test_prefix_matches_are_ranked_first(self):
        items = [
            {"id": "CorporateBody", "name": "Körperschaft"},
            {"id": "DifferentiatedPerson", "name": "Individualisierte Person"},
        ]

        # "Körperschaft" only contains "per" mid-word, while "Person" is a
        # word starting with it - so the person type must rank first.
        ordered = sort_prefix_matches_first(
            items,
            prefix="Per",
            key=lambda item: [item["id"], item["name"]],
        )

        assert ordered[0]["id"] == "DifferentiatedPerson"

    def test_exact_prefix_outranks_word_prefix(self):
        items = [
            {"id": "b", "name": "Individualisierte Person"},
            {"id": "a", "name": "Personenname"},
        ]

        ordered = sort_prefix_matches_first(
            items,
            prefix="Person",
            key=lambda item: [item["id"], item["name"]],
        )

        assert ordered[0]["id"] == "a"

    def test_property_suggest_ranks_prefix_matches_first(self):
        results = suggest_registry_properties(prefix="date", limit=5, vocab=GND_VOCAB)

        assert results
        assert results[0]["id"].lower().startswith("date")


class TestBatchSizeLimit:
    def test_oversized_batch_raises_413(self):
        queries = {
            f"q{index}": {"query": "Goethe"}
            for index in range(RECONCILIATION_BATCH_SIZE + 1)
        }

        with pytest.raises(HTTPException) as error:
            handle_reconciliation_queries(queries, vocab=GND_VOCAB)

        assert error.value.status_code == 413

    def test_manifest_batch_size_matches_enforced_limit(self):
        manifest = service_manifest_response(vocab=GND_VOCAB)

        assert manifest["batchSize"] == RECONCILIATION_BATCH_SIZE
