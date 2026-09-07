"""
Minimal, hand-rolled N-Triples parser for Getty Vocabulary Program explicit
exports.

Deliberately NOT using rdflib: the input is well-formed, ASCII-only
(non-ASCII characters are `\\uXXXX`-escaped), one-triple-per-line N-Triples
with no blank nodes (verified against real Getty AAT explicit.zip exports,
see repo memory "GETTY AAT EXPLICIT EXPORT — VERIFIED FILE SCHEMA"). A tiny
purpose-built parser is faster and has zero extra dependencies for the
~6 million lines across the AAT export files.
"""

import re
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

_ESCAPE_PATTERN = re.compile(r"\\(u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8}|.)")

_SIMPLE_ESCAPES = {
    "n": "\n",
    "r": "\r",
    "t": "\t",
    '"': '"',
    "'": "'",
    "\\": "\\",
}


class Triple(NamedTuple):
    subject: str
    predicate: str
    obj: str
    is_literal: bool
    lang: str | None
    datatype: str | None


def _unescape(text: str) -> str:
    """
    Decodes N-Triples string escapes (\\uXXXX, \\UXXXXXXXX, \\", \\\\, \\n, ...).
    """

    if "\\" not in text:
        return text

    def _replace(match: re.Match[str]) -> str:
        token = match.group(1)

        if token[0] in ("u", "U"):
            return chr(int(token[1:], 16))

        return _SIMPLE_ESCAPES.get(token, token)

    return _ESCAPE_PATTERN.sub(_replace, text)


def _parse_literal_object(object_part: str) -> tuple[str, str | None, str | None] | None:
    """
    Parses a quoted literal object, e.g. `"text"`, `"text"@en` or
    `"text"^^<http://...>`. Returns (value, lang, datatype) or None if the
    literal is malformed.
    """

    length = len(object_part)
    chars: list[str] = []
    i = 1
    closing_quote_index = -1

    while i < length:
        char = object_part[i]

        if char == "\\":
            if i + 1 >= length:
                return None

            chars.append(object_part[i : i + 2])
            i += 2
            continue

        if char == '"':
            closing_quote_index = i
            break

        chars.append(char)
        i += 1

    if closing_quote_index == -1:
        return None

    value = _unescape("".join(chars))
    suffix = object_part[closing_quote_index + 1 :].strip()

    if suffix.startswith("@"):
        return value, suffix[1:], None

    if suffix.startswith("^^<") and suffix.endswith(">"):
        return value, None, suffix[3:-1]

    return value, None, None


def parse_ntriples_line(line: str) -> Triple | None:
    """
    Parses a single N-Triples line into a `Triple`.

    Returns None for blank/comment lines or lines that don't match the
    expected `<subject> <predicate> object .` shape (subject and predicate
    are always IRIs in Getty's exports).
    """

    line = line.strip()

    if not line or line.startswith("#"):
        return None

    if not line.startswith("<"):
        return None

    end_subject = line.find(">")

    if end_subject == -1:
        return None

    subject = line[1:end_subject]
    rest = line[end_subject + 1 :].lstrip()

    if not rest.startswith("<"):
        return None

    end_predicate = rest.find(">")

    if end_predicate == -1:
        return None

    predicate = rest[1:end_predicate]
    object_part = rest[end_predicate + 1 :].strip()

    if object_part.endswith("."):
        object_part = object_part[:-1].rstrip()

    if not object_part:
        return None

    if object_part.startswith("<"):
        end_object = object_part.rfind(">")

        if end_object == -1:
            return None

        return Triple(subject, predicate, object_part[1:end_object], False, None, None)

    if object_part.startswith('"'):
        parsed = _parse_literal_object(object_part)

        if parsed is None:
            return None

        value, lang, datatype = parsed

        return Triple(subject, predicate, value, True, lang, datatype)

    return None


def iter_triples(path: Path) -> Iterator[Triple]:
    """
    Streams all valid triples from an N-Triples file.
    """

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            triple = parse_ntriples_line(line)

            if triple is not None:
                yield triple


def iter_subject_groups(path: Path) -> Iterator[tuple[str, list[Triple]]]:
    """
    Groups consecutive triples sharing the same subject.

    Assumes the file is subject-sorted (verified true for Getty's
    `*_1Subjects.nt`, `*_2Terms.nt`, `*_ScopeNotes.nt` and
    `*_ObsoleteSubjects.nt` exports - consecutive lines share the same
    subject IRI). Do NOT use this for `*_HierarchicalRels.nt` or
    `*_AssociativeRels.nt`, which are not reliably subject-sorted; build a
    plain dict from `iter_triples()` for those instead.
    """

    current_subject: str | None = None
    current_group: list[Triple] = []

    for triple in iter_triples(path):
        if triple.subject != current_subject:
            if current_group and current_subject is not None:
                yield current_subject, current_group

            current_subject = triple.subject
            current_group = [triple]
        else:
            current_group.append(triple)

    if current_group and current_subject is not None:
        yield current_subject, current_group
