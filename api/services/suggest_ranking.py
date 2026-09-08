"""
Shared ranking helper for the Reconciliation API suggest services.

Reconciliation API 0.2 expects suggest services to "perform prefix search on
their database of records, such that a suggest service can be used to provide
auto-completion as users type names or identifiers in a field".

The suggest endpoints keep substring/full-text matches for recall, so this
helper re-ranks them: values starting with the prefix come first, values with
a *word* starting with the prefix come next (so "Per" surfaces
"Individualisierte Person" ahead of "Körperschaft"), and plain substring hits
come last.
"""

from typing import Any, Callable

_EXACT_PREFIX = 0
_WORD_PREFIX = 1
_SUBSTRING = 2


def prefix_match_rank(values: list[Any], prefix: str) -> int:
    """
    Returns the best (lowest) prefix-match rank across `values`.
    """

    normalized_prefix = prefix.strip().lower()

    if not normalized_prefix:
        return _EXACT_PREFIX

    rank = _SUBSTRING

    for value in values:
        normalized_value = str(value or "").strip().lower()

        if not normalized_value:
            continue

        if normalized_value.startswith(normalized_prefix):
            return _EXACT_PREFIX

        if any(word.startswith(normalized_prefix) for word in normalized_value.split()):
            rank = min(rank, _WORD_PREFIX)

    return rank


def sort_prefix_matches_first(
    items: list[Any],
    prefix: str,
    key: Callable[[Any], list[Any]],
) -> list[Any]:
    """
    Stable-sorts suggest results so that real prefix matches come first.
    """

    if not prefix or not prefix.strip():
        return list(items)

    return sorted(items, key=lambda item: prefix_match_rank(key(item), prefix))
