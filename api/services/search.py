from typing import Any

from opensearchpy import OpenSearch

import os
import re

from api.services.property_matching import calculate_property_bonus

INDEX_NAME = os.getenv("GND_INDEX_NAME", "gnd")

OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST", "opensearch")
OPENSEARCH_PORT = int(os.getenv("OPENSEARCH_PORT", "9200"))

INDEX_NAME = "gnd"

AUTHORITY_RESOURCE_TYPE = {
    "id": "AuthorityResource",
    "name": "Authority Resource",
}

GND_TYPE_LABELS = {
    "SubjectHeadingSensoStricto": {
        "name": "Sachbegriff",
        "broader": {
            "id": "SubjectHeading",
            "name": "Subject Heading",
        },
    },
    "ProductNameOrBrandName": {
        "name": "Produktname oder Markenname",
        "broader": {
            "id": "SubjectHeading",
            "name": "Subject Heading",
        },
    },
    "EthnographicName": {
        "name": "Ethnografikum",
        "broader": {
            "id": "SubjectHeading",
            "name": "Subject Heading",
        },
    },
    "DifferentiatedPerson": {
        "name": "Individualisierte Person",
        "broader": {
            "id": "Person",
            "name": "Person",
        },
    },
    "UndifferentiatedPerson": {
        "name": "Nicht-individualisierte Person",
        "broader": {
            "id": "Person",
            "name": "Person",
        },
    },
    "CorporateBody": {
        "name": "Körperschaft",
        "broader": {
            "id": "CorporateBody",
            "name": "Corporate Body",
        },
    },
    "ConferenceOrEvent": {
        "name": "Konferenz oder Ereignis",
        "broader": {
            "id": "ConferenceOrEvent",
            "name": "Conference or Event",
        },
    },
    "PlaceOrGeographicName": {
        "name": "Geografikum",
        "broader": {
            "id": "PlaceOrGeographicName",
            "name": "Place or Geographic Name",
        },
    },
    "Work": {
        "name": "Werk",
        "broader": {
            "id": "Work",
            "name": "Work",
        },
    },
    "Family": {
        "name": "Familie",
        "broader": {
            "id": "AuthorityResource",
            "name": "Normdatenressource",
        },
    },
}

GND_TYPE_LABELS.update(
    {
        "TerritorialCorporateBodyOrAdministrativeUnit": {
            "name": "Gebietskörperschaft / Verwaltungseinheit",
            "broader": {
                "id": "PlaceOrGeographicName",
                "name": "Place or Geographic Name",
            },
        },
        "NameOfSmallGeographicUnitLyingWithinAnotherGeographicUnit": {
            "name": "Kleinräumige geografische Einheit",
            "broader": {
                "id": "PlaceOrGeographicName",
                "name": "Place or Geographic Name",
            },
        },
        "WayBorderOrLine": {
            "name": "Weg, Grenze oder Linie",
            "broader": {
                "id": "PlaceOrGeographicName",
                "name": "Place or Geographic Name",
            },
        },
        "BuildingOrMemorial": {
            "name": "Bauwerk oder Denkmal",
            "broader": {
                "id": "PlaceOrGeographicName",
                "name": "Place or Geographic Name",
            },
        },
    }
)

GND_TYPE_LABELS["AuthorityResource"] = {
    "name": "Authority Resource",
}

GND_TYPE_ALIASES = {
    "Person": [
        "DifferentiatedPerson",
        "UndifferentiatedPerson",
        "RoyalOrMemberOfARoyalHouse",
        "LiteraryOrLegendaryCharacter",
        "CollectivePseudonym",
        "Gods",
        "Spirits",
    ],

    "DifferentiatedPerson": [
        "DifferentiatedPerson",
    ],

    "Family": [
        "Family",
    ],

    "CorporateBody": [
        "CorporateBody",
        "Company",
        "MusicalCorporateBody",
        "OrganOfCorporateBody",
    ],

    "ConferenceOrEvent": [
        "ConferenceOrEvent",
        "SeriesOfConferenceOrEvent",
        "HistoricSingleEventOrEra",
    ],

    "PlaceOrGeographicName": [
        "PlaceOrGeographicName",
        "TerritorialCorporateBodyOrAdministrativeUnit",
        "Country",
        "AdministrativeUnit",
        "MemberState",
        "NaturalGeographicUnit",
        "NameOfSmallGeographicUnitLyingWithinAnotherGeographicUnit",
        "WayBorderOrLine",
        "BuildingOrMemorial",
    ],

    "SubjectHeading": [
        "SubjectHeadingSensoStricto",
        "ProductNameOrBrandName",
        "EthnographicName",
        "SoftwareProduct",
    ],

    "Work": [
        "Work",
        "MusicalWork",
        "Manuscript",
        "Collection",
    ],
}


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
) -> list[dict[str, Any]]:
    """
    Searches the local GND OpenSearch index.

    Returns results in a format that can later be used by
    the OpenRefine Reconciliation API.

    Args:
        query: The search query, e.g. "Goethe".
        limit: Maximum number of results.
        entity_type: Optional GND entity type filter, e.g. "Person".
        properties: Optional list of property filters

    Returns:
        A list of candidate matches.
    """

    if not query or not query.strip():
        return []

    search_body = build_search_body(
        query=query.strip(),
        limit=limit,
        entity_type=entity_type,
        properties=properties or [],
    )

    response = client.search(
        index=INDEX_NAME,
        body=search_body,
    )

    return format_search_results(response=response, 
                                query=query,
                                requested_type=entity_type,
                                requested_properties=properties or []
                                )

def get_gnd_record_by_id(gnd_id: str) -> dict[str, Any] | None:
    """
    Retrieves a single GND record from OpenSearch by its GND ID.

    Args:
        gnd_id: The GND identifier, e.g. "118540238".

    Returns:
        The indexed GND record or None if not found.
    """

    if not gnd_id or not gnd_id.strip():
        return None

    try:
        response = client.get(
            index=INDEX_NAME,
            id=gnd_id.strip(),
        )
    except Exception:
        return None

    if not response.get("found"):
        return None

    return response.get("_source")



def build_search_body(
    query: str,
    limit: int,
    entity_type: str | None = None,
    properties: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Builds the OpenSearch query.

    Search strategy:
    - preferredName is weighted highest
    - variantName is also important
    - id is searchable for direct GND-ID lookups
    - fuzziness allows approximate matches
    """
    properties = properties or []

    should_clauses: list[dict[str, Any]] = [
        {
            "term": {
                "id": {
                    "value": query,
                    "boost": 20
                }
            }
        },
        {
            "term": {
                "preferredName.keyword": {
                    "value": query,
                    "boost": 15
                }
            }
        },
        {
            "term": {
                "preferredName.lowercase": {
                    "value": query.lower(),
                    "boost": 12
                }
            }
        },
        {
            "term": {
                "variantName.keyword": {
                    "value": query,
                    "boost": 10
                }
            }
        },
        {
            "term": {
                "variantName.lowercase": {
                    "value": query.lower(),
                    "boost": 8
                }
            }
        },
        {
            "multi_match": {
                "query": query,
                "fields": [
                    "preferredName^5",
                    "variantName^3",
                    "id^10"
                ],
                "operator": "and",
                "boost": 5
            }
        },
        {
            "multi_match": {
                "query": query,
                "fields": [
                    "preferredName^4",
                    "variantName^3",
                    "professionOrOccupation^2",
                    "placeOfBirth",
                    "placeOfDeath",
                    "id^5"
                ],
                "fuzziness": "AUTO",
                "operator": "or",
                "boost": 1
            }
        }
    ]

    property_should_clauses = build_property_should_clauses(properties)
    should_clauses.extend(property_should_clauses)

    filter_clauses: list[dict[str, Any]] = []

    if entity_type and entity_type != "AuthorityResource":
        allowed_types = GND_TYPE_ALIASES.get(entity_type, [entity_type])

        filter_clauses.append(
            {
                "terms": {
                    "type": allowed_types
                }
            }
        )


    return {
        "size": limit,
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
) -> list[dict[str, Any]]:
    """
    Builds OpenSearch should clauses from OpenRefine reconciliation properties.

    These clauses should boost matching candidates, not strictly filter them.
    """

    clauses: list[dict[str, Any]] = []

    for prop in properties:
        prop_id = prop.get("pid")
        value = prop.get("v")

        if not prop_id or value is None:
            continue

        values = value if isinstance(value, list) else [value]

        for item in values:
            item_value = extract_property_value_for_query(item)

            if not item_value:
                continue

            # 1. Top-level field exact/keyword match, if available
            clauses.append(
                {
                    "term": {
                        f"{prop_id}.keyword": {
                            "value": item_value,
                            "boost": 8,
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
                            "boost": 5,
                        }
                    }
                }
            )

            # 3. Generic fallback via propertiesFlat
            clauses.append(
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
                                                "boost": 4,
                                            }
                                        }
                                    },
                                ]
                            }
                        },
                        "score_mode": "max",
                    }
                }
            )

    return clauses

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
        return (
            value.get("id")
            or value.get("name")
            or value.get("str")
        )

    return str(value)

def format_search_results(
    response: dict[str, Any],
    query: str | None = None,
    requested_type: str | None = None,
    requested_properties: list[dict[str, Any]] | None = None,
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

        normalized_score = normalize_score(
            raw_score=raw_score,
            query=query,
            source=source,
            requested_type=requested_type,
            requested_properties=requested_properties or [],
        )

        result = {
            "id": source.get("id"),
            "name": source.get("preferredName"),
            "score": normalized_score,
            "match": False,
            "type": format_entity_types(source.get("type")),
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

    return results

def apply_match_decision(
    results: list[dict[str, Any]],
    requested_properties: list[dict[str, Any]] | None = None,
) -> None:
    """
    Marks at most one candidate as an automatic match.

    Conservative rules:
    - Top result must be high enough
    - Gap to second result must be large enough
    - With detail properties, a smaller gap is allowed
    """

    if not results:
        return

    requested_properties = requested_properties or []

    top_score = results[0].get("score", 0)

    if top_score < 90:
        return

    if len(results) == 1:
        results[0]["match"] = True
        return

    second_score = results[1].get("score", 0)
    score_gap = top_score - second_score

    required_gap = 6

    if requested_properties:
        required_gap = 3

    if score_gap >= required_gap:
        results[0]["match"] = True


def normalize_score(
    raw_score: float,
    query: str | None = None,
    source: dict[str, Any] | None = None,
    requested_properties: list[dict[str, Any]] | None = None,
    requested_type: str | None = None,
) -> int:
    """
    Converts an OpenSearch score into a 0-100 reconciliation score.

    More conservative scoring:
    - high scores only for very strong evidence
    - substring and fuzzy matches are capped lower
    - property details can boost, but not overpower name evidence
    """

    if not source:
        source = {}

    requested_properties = requested_properties or []

    query_normalized = normalize_text_for_scoring(query or "")

    gnd_id = str(source.get("id", ""))
    preferred_name = str(source.get("preferredName", ""))
    preferred_normalized = normalize_text_for_scoring(preferred_name)

    variant_names = source.get("variantName", [])

    if isinstance(variant_names, str):
        variant_names = [variant_names]

    variant_names_normalized = [
        normalize_text_for_scoring(str(value))
        for value in variant_names
    ]

    base_score = 0

    # 1. Exact identifier match
    if query_normalized and query_normalized == normalize_text_for_scoring(gnd_id):
        base_score = 100

    # 2. Exact preferredName match
    elif query_normalized and query_normalized == preferred_normalized:
        base_score = 96

    # 3. Exact variantName match
    elif query_normalized and query_normalized in variant_names_normalized:
        base_score = 92

    # 4. Token-based preferredName match
    elif query_normalized:
        preferred_token_score = token_match_score(
            query=query_normalized,
            candidate=preferred_normalized,
        )

        variant_token_score = 0

        for variant_name in variant_names_normalized:
            variant_token_score = max(
                variant_token_score,
                token_match_score(
                    query=query_normalized,
                    candidate=variant_name,
                ),
            )

        best_token_score = max(preferred_token_score, variant_token_score)

        if best_token_score >= 1.0:
            base_score = 88
        elif best_token_score >= 0.75:
            base_score = 82
        elif best_token_score >= 0.5:
            base_score = 70

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

    # 7. Property bonus, but capped
    property_bonus, _property_features = calculate_property_bonus(
        source=source,
        requested_properties=requested_properties,
        max_bonus=12,
    )
    if base_score < 60:
        property_bonus = min(property_bonus, 5)

    # 8. Type bonus, small only
    type_bonus = 0

    if requested_type and candidate_matches_requested_type(
        source=source,
        requested_type=requested_type,
    ):
        type_bonus = 3

    final_score = base_score + property_bonus + type_bonus

    return min(final_score, 100)

def normalize_text_for_scoring(value: Any) -> str:
    """
    Normalizes text for scoring:
    - string conversion
    - lowercase
    - whitespace normalization
    """

    value = str(value or "").strip().lower()
    return " ".join(value.split())

def token_match_score(
    query: str,
    candidate: str,
) -> float:
    """
    Computes overlap of query tokens against candidate tokens.

    Returns value between 0 and 1.
    """

    query_tokens = set(re.findall(r"\w+", query))
    candidate_tokens = set(re.findall(r"\w+", candidate))

    if not query_tokens or not candidate_tokens:
        return 0.0

    overlap = query_tokens.intersection(candidate_tokens)

    return len(overlap) / len(query_tokens)



def format_entity_types(entity_types: Any) -> list[dict[str, Any]]:
    """
    Converts stored GND type values into OpenRefine-style type objects.

    Every GND record is also returned as AuthorityResource, matching the
    behavior of the public GND/lobid reconciliation API more closely.
    """

    if not entity_types:
        entity_types = []

    if isinstance(entity_types, str):
        entity_types = [entity_types]

    if not isinstance(entity_types, list):
        entity_types = []

    formatted_types: list[dict[str, Any]] = [
        AUTHORITY_RESOURCE_TYPE
    ]

    seen_type_ids = {
        AUTHORITY_RESOURCE_TYPE["id"]
    }

    for entity_type in entity_types:
        type_id = str(entity_type)

        if not type_id:
            continue

        if type_id in seen_type_ids:
            continue

        seen_type_ids.add(type_id)

        mapping = GND_TYPE_LABELS.get(type_id)

        if mapping:
            type_object: dict[str, Any] = {
                "id": type_id,
                "name": mapping.get("name", type_id),
            }

            broader = mapping.get("broader")

            if broader:
                type_object["broader"] = [broader]

            formatted_types.append(type_object)

        else:
            formatted_types.append(
                {
                    "id": type_id,
                    "name": type_id,
                }
            )

    return formatted_types

def candidate_matches_requested_type(
    source: dict[str, Any],
    requested_type: str | None,
) -> bool:
    """
    Checks whether a candidate's type matches the requested OpenRefine type.
    """

    if not requested_type:
        return False

    if requested_type == "AuthorityResource":
        return True

    candidate_types = source.get("type", [])

    if not candidate_types:
        return False

    normalized_candidate_types = normalize_candidate_types(candidate_types)

    allowed_types = GND_TYPE_ALIASES.get(
        requested_type,
        [requested_type],
    )

    return any(
        candidate_type in allowed_types
        for candidate_type in normalized_candidate_types
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