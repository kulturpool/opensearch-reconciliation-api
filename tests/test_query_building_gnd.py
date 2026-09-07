"""
Characterization tests for api/services/search.py query construction.

Pins the exact OpenSearch query shape produced by build_search_body() /
build_property_should_clauses() so the VocabConfig refactor (Phase 2) can be
diffed against this snapshot. Includes the .lowercase -> match_phrase fix
(see /memories/repo/local_reconciliation_api.md).
"""

from api.services.search import build_property_should_clauses, build_search_body


class TestBuildSearchBody:
    def test_basic_query_shape(self):
        body = build_search_body(query="Goethe", limit=5)

        assert body["size"] == 5
        assert body["_source"]["includes"] == [
            "id",
            "uri",
            "preferredName",
            "variantName",
            "type",
            "dateOfBirth",
            "dateOfDeath",
            "dateOfBirthAndDeath",
            "professionOrOccupation",
            "placeOfBirth",
            "placeOfDeath",
            "propertiesFlat",
        ]

        should = body["query"]["bool"]["should"]

        assert {"term": {"id": {"value": "Goethe", "boost": 20}}} in should
        assert {
            "term": {"preferredName.keyword": {"value": "Goethe", "boost": 15}}
        } in should
        # .lowercase bugfix: match_phrase against the analyzed field, not a
        # term query against a non-existent ".lowercase" sub-field.
        assert {
            "match_phrase": {"preferredName": {"query": "Goethe", "boost": 12}}
        } in should
        assert {
            "term": {"variantName.keyword": {"value": "Goethe", "boost": 10}}
        } in should
        assert {
            "match_phrase": {"variantName": {"query": "Goethe", "boost": 8}}
        } in should

        assert not any("preferredName.lowercase" in str(clause) for clause in should)
        assert not any("variantName.lowercase" in str(clause) for clause in should)

    def test_entity_type_filter_uses_type_aliases(self):
        body = build_search_body(query="Goethe", limit=5, entity_type="Person")
        filters = body["query"]["bool"]["filter"]
        assert filters
        assert "terms" in filters[0]
        assert "type" in filters[0]["terms"]

    def test_authority_resource_type_is_not_filtered(self):
        body = build_search_body(query="Goethe", limit=5, entity_type="AuthorityResource")
        assert body["query"]["bool"]["filter"] == []

    def test_fuzzy_clause_skipped_for_long_queries(self):
        long_query = " ".join(["word"] * 10)  # > max_fuzzy_terms (6)
        body = build_search_body(query=long_query, limit=5)
        should = body["query"]["bool"]["should"]
        assert not any(
            "fuzziness" in clause.get("multi_match", {}) for clause in should
        )

    def test_fuzzy_clause_present_for_short_queries(self):
        body = build_search_body(query="Goethe", limit=5)
        should = body["query"]["bool"]["should"]
        assert any(
            "fuzziness" in clause.get("multi_match", {}) for clause in should
        )


class TestBuildPropertyShouldClauses:
    def test_date_property_uses_cheap_term_and_prefix_clauses(self):
        clauses = build_property_should_clauses(
            [{"pid": "dateOfBirth", "v": "1749"}]
        )
        assert {
            "term": {"dateOfBirth": {"value": "1749", "boost": 18.0}}
        } in clauses
        assert any(
            clause.get("prefix", {}).get("dateOfBirth", {}).get("value") == "1749"
            for clause in clauses
        )
        # No nested propertiesFlat join for date properties.
        assert not any("nested" in str(clause) for clause in clauses)

    def test_keyword_field_property_uses_direct_term(self):
        clauses = build_property_should_clauses([{"pid": "id", "v": "118540238"}])
        assert clauses == [
            {"term": {"id": {"value": "118540238", "boost": 21.0}}}
        ]

    def test_reliable_top_level_property_skips_nested_fallback(self):
        clauses = build_property_should_clauses(
            [{"pid": "placeOfBirth", "v": "Frankfurt"}]
        )
        assert not any("nested" in str(clause) for clause in clauses)

    def test_generic_property_includes_nested_fallback(self):
        clauses = build_property_should_clauses(
            [{"pid": "academicDegree", "v": "Dr."}]
        )
        assert any("nested" in str(clause) for clause in clauses)

    def test_values_capped_at_max_property_values(self):
        clauses = build_property_should_clauses(
            [{"pid": "id", "v": [str(i) for i in range(10)]}]
        )
        # MAX_PROPERTY_VALUES = 5, one clause per value for keyword fields
        assert len(clauses) == 5

    def test_empty_properties_returns_no_clauses(self):
        assert build_property_should_clauses([]) == []

    def test_missing_pid_or_value_is_skipped(self):
        assert build_property_should_clauses([{"pid": None, "v": "x"}]) == []
        assert build_property_should_clauses([{"pid": "x", "v": None}]) == []
