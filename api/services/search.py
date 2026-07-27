from typing import Any

from opensearchpy import OpenSearch


INDEX_NAME = "gnd"

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
        hosts=[{"host": "opensearch", "port": 9200}],
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
) -> list[dict[str, Any]]:
    """
    Searches the local GND OpenSearch index.

    Returns results in a format that can later be used by
    the OpenRefine Reconciliation API.

    Args:
        query: The search query, e.g. "Goethe".
        limit: Maximum number of results.
        entity_type: Optional GND entity type filter, e.g. "Person".

    Returns:
        A list of candidate matches.
    """

    if not query or not query.strip():
        return []

    search_body = build_search_body(
        query=query.strip(),
        limit=limit,
        entity_type=entity_type,
    )

    response = client.search(
        index=INDEX_NAME,
        body=search_body,
    )

    return format_search_results(response, query=query)

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
) -> dict[str, Any]:
    """
    Builds the OpenSearch query.

    Search strategy:
    - preferredName is weighted highest
    - variantName is also important
    - id is searchable for direct GND-ID lookups
    - fuzziness allows approximate matches
    """

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

    filter_clauses: list[dict[str, Any]] = []

    if entity_type:
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


def format_search_results(
    response: dict[str, Any],
    query: str | None = None,
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
        )

        result = {
            "id": source.get("id"),
            "name": source.get("preferredName"),
            "score": normalized_score,
            "match": False,
            "type": format_entity_types(source.get("type")),
        }

        results.append(result)

    apply_match_decision(results)

    return results

def apply_match_decision(results: list[dict[str, Any]]) -> None:
    """
    Marks at most one candidate as an automatic match.

    Rule:
    - Top result must have score >= 95
    - If there is a second result, the top score must be at least 5 points higher
    - Otherwise no automatic match is assigned
    """

    if not results:
        return

    top_score = results[0].get("score", 0)

    if top_score < 95:
        return

    if len(results) == 1:
        results[0]["match"] = True
        return

    second_score = results[1].get("score", 0)

    if top_score - second_score >= 5:
        results[0]["match"] = True


def normalize_score(
    raw_score: float,
    query: str | None = None,
    source: dict[str, Any] | None = None,
) -> int:
    """
    Converts an OpenSearch score into a rough 0-100 reconciliation score.

    For the MVP we combine:
    - exact preferredName match
    - exact variantName match
    - substring match
    - fallback based on OpenSearch _score
    """

    if not source:
        source = {}

    if query:
        query_normalized = query.strip().lower()

        preferred_name = str(source.get("preferredName", "")).strip().lower()

        variant_names = source.get("variantName", [])

        if isinstance(variant_names, str):
            variant_names = [variant_names]

        variant_names_normalized = [
            str(value).strip().lower()
            for value in variant_names
        ]

        if query_normalized == preferred_name:
            return 100

        if query_normalized in variant_names_normalized:
            return 98

        if query_normalized in preferred_name:
            return 92

        for variant_name in variant_names_normalized:
            if query_normalized in variant_name:
                return 90

    if raw_score <= 0:
        return 0

    # Fallback for fuzzy / partial OpenSearch matches.
    score = round(raw_score * 35)

    return min(score, 89)


def is_likely_match(score: int) -> bool:
    """
    Determines whether a result should be treated as an automatic match.
    """

    return score >= 85


def format_entity_types(entity_types: Any) -> list[dict[str, Any]]:
    """
    Converts entity type values into OpenRefine-style type objects.

    Keeps the original fine-grained GND type as id, but adds readable labels
    and broader types where known.
    """

    if not entity_types:
        return []

    if isinstance(entity_types, str):
        entity_types = [entity_types]

    if not isinstance(entity_types, list):
        return []

    formatted_types = []

    for entity_type in entity_types:
        type_id = str(entity_type)

        mapping = GND_TYPE_LABELS.get(type_id)

        if mapping:
            type_object = {
                "id": type_id,
                "name": mapping["name"],
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