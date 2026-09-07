"""
Unit tests for importer/ntriples.py's parse_ntriples_line().

Covers the concrete line shapes seen in Getty's explicit N-Triples exports:
plain IRI objects, plain string literals, language-tagged literals,
datatyped literals, \\uXXXX escapes, and malformed/blank/comment lines.
"""

from importer.ntriples import parse_ntriples_line


class TestParseNtriplesLine:
    def test_iri_object(self):
        line = (
            "<http://vocab.getty.edu/aat/300007466> "
            "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type> "
            "<http://www.w3.org/2004/02/skos/core#Concept> .\n"
        )
        triple = parse_ntriples_line(line)

        assert triple is not None
        assert triple.subject == "http://vocab.getty.edu/aat/300007466"
        assert triple.predicate == "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
        assert triple.obj == "http://www.w3.org/2004/02/skos/core#Concept"
        assert triple.is_literal is False
        assert triple.lang is None
        assert triple.datatype is None

    def test_plain_string_literal(self):
        line = (
            '<http://vocab.getty.edu/aat/300007466_term> '
            '<http://www.w3.org/2008/05/skos-xl#literalForm> '
            '"painting (image-making)" .\n'
        )
        triple = parse_ntriples_line(line)

        assert triple is not None
        assert triple.obj == "painting (image-making)"
        assert triple.is_literal is True
        assert triple.lang is None
        assert triple.datatype is None

    def test_language_tagged_literal(self):
        line = (
            '<http://vocab.getty.edu/aat/300007466_term> '
            '<http://www.w3.org/2008/05/skos-xl#literalForm> '
            '"painting (image-making)"@en .\n'
        )
        triple = parse_ntriples_line(line)

        assert triple is not None
        assert triple.obj == "painting (image-making)"
        assert triple.is_literal is True
        assert triple.lang == "en"
        assert triple.datatype is None

    def test_datatyped_literal(self):
        line = (
            '<http://vocab.getty.edu/aat/300007466> '
            '<http://vocab.getty.edu/ontology#estStart> '
            '"1990"^^<http://www.w3.org/2001/XMLSchema#gYear> .\n'
        )
        triple = parse_ntriples_line(line)

        assert triple is not None
        assert triple.obj == "1990"
        assert triple.is_literal is True
        assert triple.lang is None
        assert triple.datatype == "http://www.w3.org/2001/XMLSchema#gYear"

    def test_unicode_escape_is_decoded(self):
        line = (
            '<http://vocab.getty.edu/aat/300007466_term> '
            '<http://www.w3.org/2008/05/skos-xl#literalForm> '
            '"Caf\\u00e9 (image-making)"@en .\n'
        )
        triple = parse_ntriples_line(line)

        assert triple is not None
        assert triple.obj == "Café (image-making)"

    def test_escaped_quote_and_backslash(self):
        line = (
            '<http://vocab.getty.edu/aat/300007466_term> '
            '<http://www.w3.org/2008/05/skos-xl#literalForm> '
            '"say \\"hi\\" \\\\ ok"@en .\n'
        )
        triple = parse_ntriples_line(line)

        assert triple is not None
        assert triple.obj == 'say "hi" \\ ok'

    def test_blank_line_returns_none(self):
        assert parse_ntriples_line("\n") is None
        assert parse_ntriples_line("   ") is None

    def test_comment_line_returns_none(self):
        assert parse_ntriples_line("# a comment\n") is None

    def test_line_not_starting_with_iri_returns_none(self):
        assert parse_ntriples_line('_:blank <http://p> "x" .\n') is None

    def test_missing_predicate_iri_returns_none(self):
        assert parse_ntriples_line('<http://vocab.getty.edu/aat/1> "no predicate iri" .\n') is None

    def test_unterminated_literal_returns_none(self):
        line = (
            '<http://vocab.getty.edu/aat/1> '
            '<http://www.w3.org/2008/05/skos-xl#literalForm> '
            '"unterminated .\n'
        )
        assert parse_ntriples_line(line) is None
