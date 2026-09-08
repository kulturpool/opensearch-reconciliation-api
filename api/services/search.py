import logging
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

# Add parent directory to path to allow imports from config
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from opensearchpy import OpenSearch
from opensearchpy.exceptions import NotFoundError, OpenSearchException
from rapidfuzz import fuzz

from api.services.property_matching import calculate_property_bonus
from api.vocabularies.base import VocabConfig
from api.vocabularies.gnd import GND_VOCAB
from config import OPENSEARCH_HOST, OPENSEARCH_PORT

logger = logging.getLogger(__name__)

# Fields returned from OpenSearch during reconciliation. Keeping this list
# narrow (instead of the full GND document) noticeably reduces the amount of
# data OpenSearch has to fetch/serialize and we have to deserialize for every
# candidate, which matters a lot when a batch touches thousands of rows.
# `propertiesFlat` is kept only as a generic fallback for properties that
# don't have a dedicated top-level field.
#
# These module-level names mirror the corresponding GND_VOCAB fields and are
# kept for backward compatibility with other modules importing them directly
# from here; GND_VOCAB is now the single source of truth (see
# api/vocabularies/gnd.py). Non-GND vocabularies (e.g. Getty) pass their own
# VocabConfig via the `vocab=` parameter instead of relying on these.
RECONCILIATION_SOURCE_FIELDS = list(GND_VOCAB.source_fields)

# Date-like properties are handled with dedicated, cheap query clauses and a
# dedicated post-processing bonus/penalty instead of the generic nested
# propertiesFlat matching used for other properties.
DATE_PROPERTY_IDS = set(GND_VOCAB.date_property_ids)

# Properties that both importers (importer/normalize_gnd_lds.py and
# importer/normalize_entityfacts.py) always write to a dedicated top-level
# field, in addition to propertiesFlat. For these, the top-level term/
# match_phrase clauses alone are exhaustive, so the (much more expensive)
# nested propertiesFlat join can be skipped entirely instead of only being
# gated behind a pre-filter.
RELIABLE_TOP_LEVEL_PROPERTY_IDS = set(GND_VOCAB.reliable_top_level_property_ids)

# "id"/"uri" (and the "gndIdentifier" alias some OpenRefine templates use)
# are mapped as plain `keyword` fields (see indexer/index_gnd_lds.py), not as
# `text` with a `.keyword` sub-field. Querying "id.keyword"/"uri.keyword" -
# as the generic property clause builder does for every other property -
# silently matches nothing, wasting a should-clause for no benefit. These
# get a single direct `term` clause on the raw field instead.
KEYWORD_FIELD_PROPERTY_IDS = dict(GND_VOCAB.keyword_field_property_ids)

YEAR_RE = re.compile(r"(?<!\d)\d{3,4}(?!\d)")

# Bounds the number of values considered per requested property (see
# build_property_should_clauses) to keep should-clause count - and thus
# query cost - predictable even for oddly-shaped/multi-valued input. Applies
# uniformly across vocabularies (not part of VocabConfig).
MAX_PROPERTY_VALUES = 5




def get_opensearch_client() -> OpenSearch:
    """
    Creates an OpenSearch client for the local DevContainer setup.

    Inside the DevContainer, OpenSearch is reachable via:
    http://opensearch:9200
    """

    return OpenSearch(
        hosts=[{"host": OPENSEARCH_HOST, "port": OPENSEARCH_PORT}],
        http_compress=True,
        use_ssl=False,
        verify_certs=False,
        ssl_show_warn=False,
    )


client = get_opensearch_client()


def search_gnd(
    query: str,
    limit: int = 5,
    entity_type: str | None = None,
    properties: list[dict[str, Any]] | None = None,
    vocab: VocabConfig = GND_VOCAB,
    prefix_search: bool = False,
) -> list[dict[str, Any]]:
    """
    Searches a vocabulary's OpenSearch index (GND by default).

    Returns results in a format that can later be used by
    the OpenRefine Reconciliation API.

    Args:
        query: The search query, e.g. "Goethe".
        limit: Maximum number of results.
        entity_type: Optional entity type filter, e.g. "Person".
        properties: Optional list of property filters
        vocab: VocabConfig to search against (defaults to GND).
        prefix_search: Adds prefix clauses so partially typed names match,
            as expected of Reconciliation API suggest services.

    Returns:
        A list of candidate matches.
    """

    if not query or not query.strip():
        # Reconciliation API 0.2 requires at least one of `query` or
        # `properties`; a property-only query is valid and must still
        # retrieve candidates.
        if not properties:
            return []

        normalized_query = ""
    else:
        normalized_query = vocab.normalize_identifier(query)

    search_body = build_search_body(
        query=normalized_query,
        limit=limit,
        entity_type=entity_type,
        properties=properties or [],
        vocab=vocab,
        prefix_search=prefix_search,
    )

    response = client.search(
        index=vocab.index_name,
        body=search_body,
    )

    return format_search_results(
        response=response,
        query=normalized_query,
        requested_type=entity_type,
        requested_properties=properties or [],
        vocab=vocab,
    )


def search_gnd_batch(
    query_specs: list[dict[str, Any]],
    vocab: VocabConfig = GND_VOCAB,
) -> tuple[list[list[dict[str, Any]]], dict[str, float]]:
    """
    Executes many reconciliation queries in a single OpenSearch `_msearch`
    request instead of one `search()` HTTP round-trip per OpenRefine row.

    This is the main lever for reconciliation throughput on large batches:
    instead of e.g. 50 sequential network calls per OpenRefine batch, we
    issue a single request that OpenSearch executes internally.

    Args:
        query_specs: list of dicts, each with keys:
            - query: str
            - limit: int
            - entity_type: str | None
            - properties: list[dict]

    Returns:
        A tuple of:
        - results per query spec, in the same order as `query_specs`
        - timing dict with `opensearch_ms` and `postprocessing_ms`
    """

    timing = {"opensearch_ms": 0.0, "postprocessing_ms": 0.0}

    if not query_specs:
        return [], timing

    msearch_body: list[dict[str, Any]] = []
    has_query: list[bool] = []

    normalized_queries: list[str] = []

    for spec in query_specs:
        query_text = (spec.get("query") or "").strip()
        spec_properties = spec.get("properties") or []

        # Reconciliation API 0.2: "At least one of query or properties must
        # be supplied" - a query object carrying only `properties` is valid
        # and must still be executed against the index.
        if not query_text and not spec_properties:
            has_query.append(False)
            continue

        normalized_query = (
            vocab.normalize_identifier(query_text) if query_text else ""
        )
        normalized_queries.append(normalized_query)
        has_query.append(True)

        msearch_body.append({"index": vocab.index_name})
        msearch_body.append(
            build_search_body(
                query=normalized_query,
                limit=spec.get("limit", 5),
                entity_type=spec.get("entity_type"),
                properties=spec_properties,
                vocab=vocab,
            )
        )

    responses: list[dict[str, Any]] = []

    if msearch_body:
        opensearch_start = time.perf_counter()
        raw_response = client.msearch(body=msearch_body)
        timing["opensearch_ms"] = (time.perf_counter() - opensearch_start) * 1000
        responses = raw_response.get("responses", [])

    results: list[list[dict[str, Any]]] = []
    response_iter = iter(responses)
    normalized_query_iter = iter(normalized_queries)

    postprocessing_start = time.perf_counter()

    for spec, query_present in zip(query_specs, has_query):
        if not query_present:
            results.append([])
            continue

        response = next(response_iter, {})
        normalized_query = next(normalized_query_iter, spec.get("query"))

        if response.get("error"):
            logger.warning(
                "OpenSearch msearch sub-query failed: %s", response.get("error")
            )
            results.append([])
            continue

        results.append(
            format_search_results(
                response=response,
                query=normalized_query,
                requested_type=spec.get("entity_type"),
                requested_properties=spec.get("properties") or [],
                vocab=vocab,
            )
        )

    timing["postprocessing_ms"] = (time.perf_counter() - postprocessing_start) * 1000

    return results, timing


def get_gnd_record_by_id(
    gnd_id: str,
    vocab: VocabConfig = GND_VOCAB,
) -> dict[str, Any] | None:
    """
    Retrieves a single record from a vocabulary's OpenSearch index by ID
    (GND by default).

    Args:
        gnd_id: The identifier, e.g. "118540238".
        vocab: VocabConfig to look the record up in (defaults to GND).

    Returns:
        The indexed record or None if not found.
    """

    if not gnd_id or not gnd_id.strip():
        return None

    try:
        response = client.get(
            index=vocab.index_name,
            id=vocab.normalize_identifier(gnd_id),
        )
    except (NotFoundError, OpenSearchException):
        return None

    if not response.get("found"):
        return None

    return response.get("_source")


def build_search_body(
    query: str,
    limit: int,
    entity_type: str | None = None,
    properties: list[dict[str, Any]] | None = None,
    vocab: VocabConfig = GND_VOCAB,
    prefix_search: bool = False,
) -> dict[str, Any]:
    """
    Builds the OpenSearch query.

    Search strategy:
    - preferredName is weighted highest
    - variantName is also important
    - id is searchable for direct ID lookups
    - fuzziness allows approximate matches

    Reconciliation API 0.2 allows a query to supply `properties` without a
    `query` string ("At least one of query or properties must be supplied").
    In that case all name-based clauses are omitted and the requested
    properties alone drive candidate retrieval.
    """
    properties = properties or []
    query = (query or "").strip()

    should_clauses: list[dict[str, Any]] = []

    if query:
        should_clauses.extend(
            [
                {"term": {"id": {"value": query, "boost": vocab.id_boost}}},
                {
                    "term": {
                        "preferredName.keyword": {
                            "value": query,
                            "boost": vocab.preferred_keyword_boost,
                        }
                    }
                },
                # NOTE: preferredName/variantName have no ".lowercase" sub-field
                # in the index mapping (only ".keyword", which is
                # case-sensitive) - see indexer/index_gnd_lds.py
                # INDEX_SETTINGS. A term query against ".lowercase" would
                # silently match nothing. match_phrase against the analyzed
                # field (gnd_text_analyzer = standard tokenizer + lowercase
                # + asciifolding) gives the intended case-insensitive
                # exact-phrase boost without requiring a mapping change/reindex.
                {
                    "match_phrase": {
                        "preferredName": {
                            "query": query,
                            "boost": vocab.preferred_phrase_boost,
                        }
                    }
                },
                {
                    "term": {
                        "variantName.keyword": {
                            "value": query,
                            "boost": vocab.variant_keyword_boost,
                        }
                    }
                },
                {
                    "match_phrase": {
                        "variantName": {
                            "query": query,
                            "boost": vocab.variant_phrase_boost,
                        }
                    }
                },
                {
                    "multi_match": {
                        "query": query,
                        "fields": list(vocab.multi_match_fields),
                        "operator": "and",
                        "boost": vocab.multi_match_boost,
                    }
                },
            ]
        )

        # Fuzzy matching multiplies clause count by (terms * fields *
        # expansions), which can exceed OpenSearch's default maxClauseCount
        # (1024) for queries with many words (e.g. long titles/descriptions
        # used as the name value). Cap expansions and skip fuzziness entirely
        # once a query has too many terms to stay safely under that limit.
        if len(query.split()) <= vocab.fuzzy_max_terms:
            should_clauses.append(
                {
                    "multi_match": {
                        "query": query,
                        "fields": list(vocab.fuzzy_fields),
                        "fuzziness": "AUTO",
                        "max_expansions": vocab.fuzzy_max_expansions,
                        "prefix_length": 1,
                        "operator": "or",
                        "boost": 1,
                    }
                }
            )

        # Suggest services are expected to perform prefix search so they can
        # drive auto-completion while the user is still typing. These clauses
        # let a partially typed last token (e.g. "Goeth") match, which the
        # analyzed match/multi_match clauses above cannot do on their own.
        if prefix_search:
            should_clauses.extend(
                [
                    {
                        "match_phrase_prefix": {
                            "preferredName": {
                                "query": query,
                                "max_expansions": vocab.fuzzy_max_expansions,
                                "boost": vocab.preferred_phrase_boost,
                            }
                        }
                    },
                    {
                        "match_phrase_prefix": {
                            "variantName": {
                                "query": query,
                                "max_expansions": vocab.fuzzy_max_expansions,
                                "boost": vocab.variant_phrase_boost,
                            }
                        }
                    },
                    {
                        "prefix": {
                            "id": {
                                "value": query,
                                "boost": vocab.id_boost,
                            }
                        }
                    },
                ]
            )

    property_should_clauses = build_property_should_clauses(properties, vocab=vocab)
    should_clauses.extend(property_should_clauses)

    filter_clauses: list[dict[str, Any]] = []

    if vocab.fixed_vocabulary:
        filter_clauses.append({"term": {"vocabulary": vocab.fixed_vocabulary}})

    if entity_type and not is_root_type(entity_type, vocab=vocab):
        allowed_types = vocab.type_aliases.get(entity_type, [entity_type])

        filter_clauses.append({"terms": {"type": allowed_types}})

    return {
        "size": limit,
        "_source": {"includes": list(vocab.source_fields)},
        "query": {
            "bool": {
                "should": should_clauses,
                "filter": filter_clauses,
                "minimum_should_match": 1,
            }
        },
    }


def build_property_should_clauses(
    properties: list[dict[str, Any]],
    vocab: VocabConfig = GND_VOCAB,
) -> list[dict[str, Any]]:
    """
    Builds OpenSearch should clauses from OpenRefine reconciliation properties.

    These clauses boost matching candidates at query time, making candidates
    with matching properties rank higher in OpenSearch results.
    The post-processing then applies penalties for mismatches.

    Date properties (dateOfBirth/dateOfDeath/dateOfBirthAndDeath) are handled
    with cheap term/prefix clauses on their (keyword) top-level fields only.
    professionOrOccupation/placeOfBirth/placeOfDeath are always written to a
    top-level field by the importers too, so they skip the nested join the
    same way. "id"/"uri"/"gndIdentifier" are plain `keyword` fields with no
    `.keyword` sub-field, so they get a single direct `term` clause instead
    of the generic (broken, for them) `.keyword` clause. For all other,
    truly generic properties (which may only exist inside `propertiesFlat`
    for a given record), the nested join is kept as a fallback but gated
    behind a cheap `availableProperties` term filter, so OpenSearch only
    pays the (expensive) nested-join cost for candidates that actually
    declare that property - not for every candidate that matches on name
    alone.
    """

    clauses: list[dict[str, Any]] = []

    for prop in properties:
        prop_id = prop.get("pid")
        value = prop.get("v")

        if not prop_id or value is None:
            continue

        values = value if isinstance(value, list) else [value]

        # Cap the number of values considered per property. OpenRefine can
        # send multi-valued columns; without a cap, a handful of properties
        # with many values each could blow up should-clause count (and thus
        # query cost) for a single row.
        values = values[:MAX_PROPERTY_VALUES]

        # Determine boost multiplier based on property importance
        # Dates and IDs are very discriminating, so boost them more
        boost_multiplier = get_property_boost_multiplier(prop_id, vocab=vocab)
        is_date_property = prop_id in vocab.date_property_ids
        keyword_field = vocab.keyword_field_property_ids.get(prop_id)
        skip_nested_fallback = prop_id in vocab.reliable_top_level_property_ids

        for item in values:
            item_value = extract_property_value_for_query(item)

            if not item_value:
                continue

            if is_date_property:
                clauses.extend(
                    build_date_property_clauses(
                        prop_id=prop_id,
                        item_value=item_value,
                        boost_multiplier=boost_multiplier,
                    )
                )
                continue

            if keyword_field:
                clauses.append(
                    {
                        "term": {
                            keyword_field: {
                                "value": item_value,
                                "boost": 14 * boost_multiplier,
                            }
                        }
                    }
                )
                continue

            # 1. Top-level field exact/keyword match, if available
            clauses.append(
                {
                    "term": {
                        f"{prop_id}.keyword": {
                            "value": item_value,
                            "boost": 12 * boost_multiplier,
                        }
                    }
                }
            )

            # 2. Top-level text match
            clauses.append(
                {
                    "match_phrase": {
                        prop_id: {
                            "query": item_value,
                            "boost": 8 * boost_multiplier,
                        }
                    }
                }
            )

            if skip_nested_fallback:
                continue

            # 3. Generic fallback via propertiesFlat, gated behind a cheap
            # `availableProperties` term check. OpenSearch evaluates cheap
            # conjunction members first, so the nested join below is only
            # actually executed for candidates that pass that check.
            clauses.append(
                {
                    "bool": {
                        "filter": [{"term": {"availableProperties": prop_id}}],
                        "must": [
                            {
                                "nested": {
                                    "path": "propertiesFlat",
                                    "query": {
                                        "bool": {
                                            "must": [
                                                {
                                                    "term": {
                                                        "propertiesFlat.id": prop_id
                                                    }
                                                },
                                                {
                                                    "match_phrase": {
                                                        "propertiesFlat.value": {
                                                            "query": item_value,
                                                            "boost": 6
                                                            * boost_multiplier,
                                                        }
                                                    }
                                                },
                                            ]
                                        }
                                    },
                                    "score_mode": "max",
                                }
                            }
                        ],
                    }
                }
            )

    return clauses


def build_date_property_clauses(
    prop_id: str,
    item_value: str,
    boost_multiplier: float,
) -> list[dict[str, Any]]:
    """
    Builds cheap OpenSearch should clauses for a date-like property value.

    - an exact term match on the field itself (matches when precision lines
      up, e.g. both sides are "1749-08-28")
    - a `prefix` match using the extracted year on the field itself and on
      `dateOfBirthAndDeath` (matches "1749" against a stored "1749-08-28" or
      a combined "1749-1832" value)

    Both clause types are plain keyword-field lookups (term/prefix), so they
    are index-lookup cheap and avoid the nested `propertiesFlat` join.
    """

    clauses: list[dict[str, Any]] = [
        {
            "term": {
                prop_id: {
                    "value": item_value,
                    "boost": 12 * boost_multiplier,
                }
            }
        }
    ]

    year = extract_year_token(item_value)

    if not year:
        return clauses

    prefix_fields = [prop_id]

    if prop_id != "dateOfBirthAndDeath":
        prefix_fields.append("dateOfBirthAndDeath")

    for field in prefix_fields:
        clauses.append(
            {
                "prefix": {
                    field: {
                        "value": year,
                        "boost": 6 * boost_multiplier,
                    }
                }
            }
        )

    return clauses


def extract_year_token(value: str) -> str | None:
    """
    Extracts the first 3-4 digit year found in a date-like value.
    """

    match = YEAR_RE.search(str(value or ""))

    return match.group(0) if match else None


def get_property_boost_multiplier(prop_id: str, vocab: VocabConfig = GND_VOCAB) -> float:
    """
    Returns a boost multiplier based on how discriminating a property is.

    High-value properties like dates and IDs get higher multipliers
    to make them more influential in OpenSearch scoring.
    """
    if prop_id in vocab.high_priority_property_ids:
        return 1.5  # 50% boost increase for dates/IDs
    elif prop_id in vocab.medium_priority_property_ids:
        return 1.25  # 25% boost increase for places
    else:
        return 1.0  # Normal boost


def extract_property_value_for_query(value: Any) -> str | None:
    """
    Converts OpenRefine property values into a searchable string.

    Values can be:
    - plain strings
    - numbers
    - reconciled values like {"id": "...", "name": "..."}
    """

    if value is None:
        return None

    if isinstance(value, dict):
        return value.get("id") or value.get("name") or value.get("str")

    return str(value)


def format_search_results(
    response: dict[str, Any],
    query: str | None = None,
    requested_type: str | None = None,
    requested_properties: list[dict[str, Any]] | None = None,
    vocab: VocabConfig = GND_VOCAB,
) -> list[dict[str, Any]]:
    """
    Converts OpenSearch hits into reconciliation-style result objects.

    Important:
    We do not mark every high-scoring candidate as match=True.
    Instead, we only mark the top candidate as match=True if it is clearly
    better than the next result. This avoids multiple automatic matches
    for ambiguous queries such as "Goethe".
    """

    hits = response.get("hits", {}).get("hits", [])

    results: list[dict[str, Any]] = []

    for hit in hits:
        source = hit.get("_source", {})
        raw_score = hit.get("_score", 0.0)

        normalized_score, signals = normalize_score(
            raw_score=raw_score,
            query=query,
            source=source,
            requested_type=requested_type,
            requested_properties=requested_properties or [],
            vocab=vocab,
        )

        result = {
            "id": source.get("id"),
            "name": source.get("preferredName"),
            "score": normalized_score,
            "match": False,
            "type": format_entity_types(source.get("type"), vocab=vocab),
            # Internal only, stripped before the result is returned below.
            "_signals": signals,
        }

        results.append(result)

    results.sort(
        key=lambda result: result.get("score", 0),
        reverse=True,
    )

    apply_match_decision(
        results=results,
        requested_properties=requested_properties or [],
    )

    for result in results:
        result.pop("_signals", None)

    return results


def apply_match_decision(
    results: list[dict[str, Any]],
    requested_properties: list[dict[str, Any]] | None = None,
) -> None:
    """
    Marks at most one candidate as an automatic match.

    Conservative rules:
    - Top result must be high enough, OR corroborated by a strong exact
      normalized name match plus a type match or a birth/death date match
    - Gap to second result must be large enough
    - With detail properties, a smaller gap is allowed
    - If the runner-up is itself an equally strong exact name match, the
      pair is treated as ambiguous and no automatic match is made
    """

    if not results:
        return

    requested_properties = requested_properties or []

    top = results[0]
    top_score = top.get("score", 0)
    top_signals = top.get("_signals") or {}

    strong_name = bool(top_signals.get("exact_name_match"))
    corroborated = strong_name and (
        top_signals.get("type_match")
        or top_signals.get("birth_match")
        or top_signals.get("death_match")
    )

    if top_score < 70 and not corroborated:
        return

    if len(results) == 1:
        if top_score >= 90 or corroborated:
            top["match"] = True
        return

    second = results[1]
    second_score = second.get("score", 0)
    second_signals = second.get("_signals") or {}
    score_gap = top_score - second_score

    # Two candidates with an equally strong exact name match are ambiguous
    # (e.g. two different people named identically) - don't auto-match.
    if second_signals.get("exact_name_match") and score_gap < 10:
        return

    if top_score >= 90:
        required_gap = 3 if requested_properties else 6
    elif corroborated:
        # Weaker base score, but strongly corroborated by type/date evidence.
        required_gap = 2
    else:
        return

    if score_gap >= required_gap:
        top["match"] = True


def normalize_score(
    raw_score: float,
    query: str | None = None,
    source: dict[str, Any] | None = None,
    requested_properties: list[dict[str, Any]] | None = None,
    requested_type: str | None = None,
    vocab: VocabConfig = GND_VOCAB,
) -> tuple[int, dict[str, bool]]:
    """
    Converts an OpenSearch score into a 0-100 reconciliation score.

    More conservative scoring:
    - high scores only for very strong evidence
    - substring and fuzzy matches are capped lower
    - property details can boost, but not overpower name evidence

    Returns a tuple of (score, signals). `signals` carries a few booleans
    (exact_name_match, type_match, birth_match, death_match) used by
    `apply_match_decision` to decide on automatic matches; it is not part of
    the OpenRefine-facing result.
    """

    if not source:
        source = {}

    requested_properties = requested_properties or []

    query_normalized = normalize_person_name(query or "")
    query_signature = name_signature(query or "")

    gnd_id = str(source.get("id", ""))
    preferred_name = str(source.get("preferredName", ""))
    preferred_normalized = normalize_person_name(preferred_name)
    preferred_signature = name_signature(preferred_name)

    variant_names = source.get("variantName", [])

    if isinstance(variant_names, str):
        variant_names = [variant_names]

    variant_names_normalized = [
        normalize_person_name(str(value)) for value in variant_names
    ]
    variant_signatures = [name_signature(str(value)) for value in variant_names]

    base_score = 0
    exact_name_match = False

    # 1. Exact identifier match
    if query_normalized and query_normalized == normalize_person_name(gnd_id):
        base_score = 100

    # 2. Exact preferredName match, including GND's inverted "Last, First"
    # order vs. a natural-order query (or vice versa) - both normalize to
    # the same order-independent token signature.
    elif query_normalized and (
        query_normalized == preferred_normalized
        or (query_signature and query_signature == preferred_signature)
    ):
        base_score = 96
        exact_name_match = True

    # 3. Exact variantName match (same inversion-aware comparison)
    elif query_normalized and (
        query_normalized in variant_names_normalized
        or (query_signature and query_signature in variant_signatures)
    ):
        base_score = 92
        exact_name_match = True

    # 4. Fuzzy/token-based name match using rapidfuzz's token_sort_ratio,
    # which is inherently order-independent (also helps with inverted
    # names) and tolerant of small typos/differences.
    elif query_normalized:
        preferred_ratio = (
            fuzz.token_sort_ratio(query_normalized, preferred_normalized)
            if preferred_normalized
            else 0
        )

        variant_ratio = max(
            (
                fuzz.token_sort_ratio(query_normalized, variant_name)
                for variant_name in variant_names_normalized
                if variant_name
            ),
            default=0,
        )

        best_ratio = max(preferred_ratio, variant_ratio)

        if best_ratio >= 95:
            base_score = 88
        elif best_ratio >= 85:
            base_score = 82
        elif best_ratio >= 70:
            base_score = 70
        elif best_ratio >= 55:
            base_score = 60

    # 5. Substring matches, capped lower
    if query_normalized and base_score == 0:
        if query_normalized in preferred_normalized:
            base_score = 78
        else:
            for variant_name in variant_names_normalized:
                if query_normalized in variant_name:
                    base_score = 74
                    break

    # 6. OpenSearch fallback, capped lower
    if base_score == 0:
        if raw_score <= 0:
            base_score = 0
        else:
            base_score = min(round(raw_score * 18), 72)

    # 7. Property bonus and penalty.
    # Date properties (dateOfBirth/dateOfDeath/dateOfBirthAndDeath) are
    # scored separately below via `score_date_signals`, so they're excluded
    # here to avoid double-counting.
    non_date_properties = [
        prop
        for prop in requested_properties
        if prop.get("pid") not in vocab.date_property_ids
    ]

    property_bonus, property_penalty, _property_features = calculate_property_bonus(
        source=source,
        requested_properties=non_date_properties,
        max_bonus=10,
        max_penalty=12,
    )

    if vocab.uses_date_signals:
        date_signals = score_date_signals(
            source=source,
            requested_properties=requested_properties,
        )
    else:
        date_signals = {
            "bonus": 0,
            "penalty": 0,
            "birth_match": False,
            "death_match": False,
        }

    property_bonus += date_signals["bonus"]
    property_penalty += date_signals["penalty"]

    # Properties are meant to be *additional* corroborating evidence, not a
    # replacement for actual name evidence. Without this, a handful of
    # matching properties (e.g. birth/death year) could push a candidate
    # with a weak/wrong name match above the auto-match threshold, which is
    # exactly the opposite of what we want. So the maximum bonus properties
    # may contribute is capped based on how strong the name match already
    # is - strong name evidence gets to use (most of) the full bonus,
    # while a weak/fallback name match gets only a token amount.
    #
    # Exception: for a property-only query (allowed by Reconciliation API
    # 0.2 when no `query` string is supplied), the properties *are* the only
    # evidence available, so capping them against a non-existent name match
    # would flatten every candidate to the same score.
    if query_normalized:
        property_bonus = min(
            property_bonus, max_property_bonus_for_base_score(base_score)
        )

    # 8. Type bonus
    type_bonus = 0
    type_match = bool(
        requested_type
        and candidate_matches_requested_type(
            source=source,
            requested_type=requested_type,
            vocab=vocab,
        )
    )

    if type_match:
        type_bonus = min(6, max_property_bonus_for_base_score(base_score))

    final_score = base_score + property_bonus + type_bonus - property_penalty

    signals = {
        "exact_name_match": exact_name_match,
        "type_match": type_match,
        "birth_match": date_signals["birth_match"],
        "death_match": date_signals["death_match"],
    }

    return min(final_score, 100), signals


def max_property_bonus_for_base_score(base_score: int) -> int:
    """
    Caps how much requested-property evidence (dates, places, occupation,
    etc.) may contribute to the final score, based on how strong the name
    match already is.

    Properties are meant to be *additional*, corroborating evidence on top
    of a name match - not a way for a wrong/weak name match to be pushed
    into automatic-match territory. So the better the name match already is,
    the more headroom property bonuses get; a weak/fallback name match gets
    only a token amount, no matter how many properties line up.
    """

    if base_score >= 92:  # exact identifier/name/variant match
        return 20

    if base_score >= 82:  # strong fuzzy name match
        return 12

    if base_score >= 70:  # moderate fuzzy/substring name match
        return 6

    if base_score >= 60:  # weak fuzzy name match
        return 3

    return 1  # OpenSearch fallback only - essentially no real name evidence


def score_date_signals(
    source: dict[str, Any],
    requested_properties: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Fast, dedicated scoring for dateOfBirth/dateOfDeath/dateOfBirthAndDeath.

    Rules:
    - an exact shared birth year gives a bonus
    - an exact shared death year gives a bonus
    - both birth and death matching gives an additional, strong bonus
    - a birth/death year that's off by a single year (common transcription
      fuzziness) gets a small bonus instead of a penalty
    - a clearly different year is penalized, but moderately (dates in GND
      can be approximate/fuzzy too)
    """

    requested_birth_years: set[str] = set()
    requested_death_years: set[str] = set()

    for prop in requested_properties:
        prop_id = prop.get("pid")
        value = prop.get("v")

        if prop_id == "dateOfBirth":
            requested_birth_years |= extract_years(value)
        elif prop_id == "dateOfDeath":
            requested_death_years |= extract_years(value)
        elif prop_id == "dateOfBirthAndDeath":
            birth_year, death_year = split_combined_date_years(extract_years(value))

            if birth_year:
                requested_birth_years.add(birth_year)

            if death_year:
                requested_death_years.add(death_year)

    if not requested_birth_years and not requested_death_years:
        return {"bonus": 0, "penalty": 0, "birth_match": False, "death_match": False}

    candidate_birth_years = extract_years(source.get("dateOfBirth"))
    candidate_death_years = extract_years(source.get("dateOfDeath"))

    combined_birth_year, combined_death_year = split_combined_date_years(
        extract_years(source.get("dateOfBirthAndDeath"))
    )

    if combined_birth_year:
        candidate_birth_years.add(combined_birth_year)

    if combined_death_year:
        candidate_death_years.add(combined_death_year)

    bonus = 0
    penalty = 0
    birth_match = False
    death_match = False

    if requested_birth_years:
        if requested_birth_years & candidate_birth_years:
            birth_match = True
            bonus += 14
        elif candidate_birth_years:
            if years_within_tolerance(requested_birth_years, candidate_birth_years):
                bonus += 4
            else:
                penalty += 6

    if requested_death_years:
        if requested_death_years & candidate_death_years:
            death_match = True
            bonus += 14
        elif candidate_death_years:
            if years_within_tolerance(requested_death_years, candidate_death_years):
                bonus += 4
            else:
                penalty += 6

    if birth_match and death_match:
        bonus += 10

    return {
        "bonus": bonus,
        "penalty": penalty,
        "birth_match": birth_match,
        "death_match": death_match,
    }


def extract_years(value: Any) -> set[str]:
    """
    Extracts all 3-4 digit years found in a value (or list of values).
    """

    if value is None:
        return set()

    if isinstance(value, list):
        years: set[str] = set()

        for item in value:
            years |= extract_years(item)

        return years

    if isinstance(value, dict):
        return extract_years(value.get("id") or value.get("name") or value.get("str"))

    return set(YEAR_RE.findall(str(value)))


def split_combined_date_years(years: set[str]) -> tuple[str | None, str | None]:
    """
    Splits a set of years extracted from a combined "dateOfBirthAndDeath"
    value (e.g. "1749-1832") into (birth_year, death_year).

    With a single year, both birth and death fall back to that same year
    since precision doesn't allow telling them apart.
    """

    if not years:
        return None, None

    ordered = sorted(years)

    if len(ordered) == 1:
        return ordered[0], ordered[0]

    return ordered[0], ordered[-1]


def years_within_tolerance(
    requested_years: set[str],
    candidate_years: set[str],
    tolerance: int = 1,
) -> bool:
    """
    Checks whether any requested year is within `tolerance` years of any
    candidate year. Used to soften small, likely transcription-related
    off-by-one-year differences instead of treating them as a hard mismatch.
    """

    for requested_year in requested_years:
        for candidate_year in candidate_years:
            try:
                if abs(int(requested_year) - int(candidate_year)) <= tolerance:
                    return True
            except ValueError:
                continue

    return False


def normalize_person_name(value: Any) -> str:
    """
    Normalizes a name (or query string) for comparison:
    - string conversion
    - diacritics stripped (e.g. "Müller" -> "muller")
    - lowercase
    - punctuation normalized to whitespace (commas, periods, etc.)
    - whitespace normalization
    """

    value = str(value or "")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.lower()
    value = re.sub(r"[.,;:!?'\"()\[\]/]", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def name_signature(value: Any) -> str:
    """
    Builds an order-independent signature of a normalized name by sorting
    its tokens.

    This makes inverted GND names like "Goethe, Johann Wolfgang von" compare
    equal to a natural-order query like "Johann Wolfgang von Goethe", since
    both normalize to the same sorted token sequence.
    """

    tokens = sorted(normalize_person_name(value).split())

    return " ".join(tokens)


def format_entity_types(
    entity_types: Any,
    vocab: VocabConfig = GND_VOCAB,
) -> list[dict[str, Any]]:
    """
    Converts stored type values into OpenRefine-style type objects.

    Every record is also returned as vocab.root_type (e.g. AuthorityResource
    for GND), matching the behavior of the public GND/lobid reconciliation
    API more closely. Vocabularies without a catch-all root type (root_type
    is None) skip this.
    """

    if not entity_types:
        entity_types = []

    if isinstance(entity_types, str):
        entity_types = [entity_types]

    if not isinstance(entity_types, list):
        entity_types = []

    formatted_types: list[dict[str, Any]] = []
    seen_type_ids: set[str] = set()

    if vocab.root_type:
        formatted_types.append(vocab.root_type)
        seen_type_ids.add(vocab.root_type["id"])

    for entity_type in entity_types:
        raw_type_id = str(entity_type)

        if not raw_type_id:
            continue

        mapping = vocab.type_labels.get(raw_type_id)

        # A mapping may collapse several concrete stored type values onto a
        # single coarser type id (e.g. Getty's combined /getty vocab maps
        # "aat:Concept", "aat:Facet", ... all onto "aat"), so dedup on the
        # *resolved* id rather than the raw stored value.
        resolved_id = mapping.get("id", raw_type_id) if mapping else raw_type_id

        if resolved_id in seen_type_ids:
            continue

        seen_type_ids.add(resolved_id)

        if mapping:
            type_object: dict[str, Any] = {
                "id": resolved_id,
                "name": mapping.get("name", raw_type_id),
            }

            broader = mapping.get("broader")

            if broader:
                type_object["broader"] = [broader]

            formatted_types.append(type_object)

        else:
            formatted_types.append(
                {
                    "id": resolved_id,
                    "name": resolved_id,
                }
            )

    return formatted_types


def is_root_type(
    entity_type: str | None,
    vocab: VocabConfig = GND_VOCAB,
) -> bool:
    """
    Returns True when the requested type equals the vocab's catch-all root
    type ID (e.g. "AuthorityResource" for GND, "aat" for Getty).
    """

    if not entity_type or not vocab.root_type:
        return False

    return entity_type == vocab.root_type.get("id")


def candidate_matches_requested_type(
    source: dict[str, Any],
    requested_type: str | None,
    vocab: VocabConfig = GND_VOCAB,
) -> bool:
    """
    Checks whether a candidate's type matches the requested OpenRefine type.
    """

    if not requested_type:
        return False

    if is_root_type(requested_type, vocab=vocab):
        return True

    candidate_types = source.get("type", [])

    if not candidate_types:
        return False

    normalized_candidate_types = normalize_candidate_types(candidate_types)

    allowed_types = vocab.type_aliases.get(
        requested_type,
        [requested_type],
    )

    return any(
        candidate_type in allowed_types for candidate_type in normalized_candidate_types
    )


def normalize_candidate_types(candidate_types: Any) -> list:
    """
    Normalizes candidate type values into a list of string IDs.

    Supports:
    - "DifferentiatedPerson"
    - ["DifferentiatedPerson", "RoyalOrMemberOfARoyalHouse"]
    - [{"id": "DifferentiatedPerson", "name": "..."}]
    """

    if candidate_types is None:
        return []

    if isinstance(candidate_types, str):
        return [candidate_types]

    if isinstance(candidate_types, dict):
        type_id = candidate_types.get("id")

        if type_id:
            return [str(type_id)]

        return []

    if isinstance(candidate_types, list):
        result: list[str] = []

        for item in candidate_types:
            if isinstance(item, str):
                result.append(item)

            elif isinstance(item, dict):
                type_id = item.get("id")

                if type_id:
                    result.append(str(type_id))

        return result

    return []
