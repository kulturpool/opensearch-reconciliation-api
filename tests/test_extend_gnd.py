"""
Characterization tests for api/services/properties.py extend formatting.

Only exercises pure-function paths (no live OpenSearch client calls) -
format_extend_value()/resolve_gnd_entity() hit the index for GND-URI-shaped
values, which is out of scope for these fast, offline characterization tests.
"""

from api.services.properties import (
    SELF_IDENTIFIER_PROPERTY_IDS,
    format_extend_values,
)


class TestSelfIdentifierShortCircuit:
    def test_id_property_is_always_plain_literal(self):
        # Even with content="id" (which would normally reformat GND-URI-like
        # values), the entity's own id/uri/gndIdentifier must pass through
        # untouched - it must never be turned into a reconciled entity object
        # pointing at itself.
        assert format_extend_values("id", "118540238", content="literal") == [
            {"str": "118540238"}
        ]
        assert format_extend_values("gndIdentifier", "118540238", content="id") == [
            {"str": "118540238"}
        ]

    def test_uri_self_identifier_not_resolved(self):
        result = format_extend_values(
            "uri", "https://d-nb.info/gnd/118540238", content="literal"
        )
        assert result == [{"str": "https://d-nb.info/gnd/118540238"}]

    def test_empty_self_identifier_returns_empty_list(self):
        assert format_extend_values("id", "", content="literal") == []

    def test_self_identifier_property_ids_contains_expected_set(self):
        assert SELF_IDENTIFIER_PROPERTY_IDS == {"id", "uri", "gndIdentifier"}


class TestFormatExtendValuesPlainLiterals:
    def test_none_value_returns_empty_list(self):
        assert format_extend_values("dateOfBirth", None) == []

    def test_plain_string_literal(self):
        result = format_extend_values("professionOrOccupation", "Novelist", content="literal")
        assert result == [{"str": "Novelist"}]

    def test_digit_and_hyphen_shaped_value_is_treated_as_gnd_id_lookup(self):
        # Quirk: any value made up only of digits/hyphens (e.g. a plain date
        # like "1749-08-28") is shaped like a GND ID, so format_extend_value()
        # attempts to resolve it against the index. When not found, it falls
        # back to a generic AuthorityResource stub instead of a plain literal.
        # This pins EXISTING behaviour, not necessarily desired behaviour.
        result = format_extend_values("dateOfBirth", "1749-08-28", content="literal")
        assert result == [
            {
                "id": "1749-08-28",
                "name": "1749-08-28",
                "type": [{"id": "AuthorityResource", "name": "Normdatenressource"}],
            }
        ]

    def test_list_value_expands_and_deduplicates(self):
        result = format_extend_values(
            "variantName", ["Goethe, J.W.", "Goethe, J.W."], content="literal"
        )
        assert result == [{"str": "Goethe, J.W."}]

    def test_dict_without_identifier_falls_back_to_label(self):
        result = format_extend_values(
            "someProperty", {"name": "A Label"}, content="literal"
        )
        assert result == [{"str": "A Label"}]
