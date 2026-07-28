import re
import unicodedata
from typing import Any


GND_URI_PREFIX = "https://d-nb.info/gnd/"
GND_VOCAB_PREFIX = "https://d-nb.info/standards/vocab/gnd/"


def calculate_property_bonus(
    source: dict[str, Any],
    requested_properties: list[dict[str, Any]],
    max_bonus: int = 20,
) -> tuple[int, list[dict[str, Any]]]:
    """
    Calculates a generic score bonus from OpenRefine detail columns.

    Works for all properties, not only person-related fields.

    Returns:
    - bonus score
    - feature list for debugging
    """

    if not requested_properties:
        return 0, []

    total_bonus = 0
    features: list[dict[str, Any]] = []

    for prop in requested_properties:
        prop_id = extract_requested_property_id(prop)
        expected_values = extract_requested_property_values(prop)

        if not prop_id or not expected_values:
            continue

        actual_values = get_candidate_property_values(
            source=source,
            prop_id=prop_id,
        )

        match_result = score_property_match(
            expected_values=expected_values,
            actual_values=actual_values,
        )

        features.append(
            {
                "id": f"property_match_{prop_id}",
                "value": match_result["matched"],
            }
        )

        features.append(
            {
                "id": f"property_score_{prop_id}",
                "value": match_result["score"],
            }
        )

        total_bonus += match_result["score"]

    return min(total_bonus, max_bonus), features


def extract_requested_property_id(prop: dict[str, Any]) -> str | None:
    """
    Extracts property id from OpenRefine reconciliation property object.

    OpenRefine usually sends:
    {"pid": "...", "v": "..."}
    """

    prop_id = prop.get("pid") or prop.get("id")

    if not prop_id:
        return None

    return str(prop_id)


def extract_requested_property_values(prop: dict[str, Any]) -> list:
    """
    Extracts requested property values from OpenRefine query object.
    """

    raw_value = prop.get("v")

    if raw_value is None:
        raw_value = prop.get("value")

    return flatten_value_to_strings(raw_value)


def get_candidate_property_values(
    source: dict[str, Any],
    prop_id: str,
) -> list:
    """
    Gets property values from a candidate record.

    Looks in:
    1. direct top-level field, e.g. source["dateOfBirth"]
    2. propertiesFlat, e.g.
       {"id": "academicDegree", "value": "Prof."}
    3. alias fallback for compact normalized fields
    """

    values: list[str] = []

    candidate_prop_ids = get_property_aliases(prop_id)

    for candidate_prop_id in candidate_prop_ids:
        direct_value = source.get(candidate_prop_id)

        if direct_value is not None:
            values.extend(flatten_value_to_strings(direct_value))

    properties_flat = source.get("propertiesFlat", [])

    if isinstance(properties_flat, list):
        for item in properties_flat:
            if not isinstance(item, dict):
                continue

            item_id = item.get("id")

            if item_id in candidate_prop_ids:
                item_value = item.get("value")

                if item_value is not None:
                    values.extend(flatten_value_to_strings(item_value))

    return deduplicate(values)


def get_property_aliases(prop_id: str) -> list:
    """
    Returns possible local field/property ids for a requested property.

    This is generic but includes a few common normalized aliases.
    It is NOT person-only.
    """

    aliases = {
        "preferredName": [
            "preferredName",
            "preferredNameForThePerson",
            "preferredNameForTheCorporateBody",
            "preferredNameForTheConferenceOrEvent",
            "preferredNameForThePlaceOrGeographicName",
            "preferredNameForTheSubjectHeading",
            "preferredNameForTheWork",
        ],
        "variantName": [
            "variantName",
            "variantNameForThePerson",
            "variantNameForTheCorporateBody",
            "variantNameForTheConferenceOrEvent",
            "variantNameForThePlaceOrGeographicName",
            "variantNameForTheSubjectHeading",
            "variantNameForTheWork",
        ],
        "id": [
            "id",
            "gndIdentifier",
        ],
        "uri": [
            "uri",
            "sameAs",
        ],
        "type": [
            "type",
        ],
    }

    if prop_id in aliases:
        return aliases[prop_id]

    return [prop_id]


def score_property_match(
    expected_values: list[str],
    actual_values: list[str],
) -> dict[str, Any]:
    """
    Compares expected values from OpenRefine with actual candidate values.

    The score is generic:
    - exact identifier/URI match: 10
    - exact normalized literal match: 8
    - compact identifier match: 8
    - containment match: 5
    - token overlap match: 3
    """

    if not expected_values or not actual_values:
        return {
            "matched": False,
            "score": 0,
        }

    best_score = 0

    for expected in expected_values:
        for actual in actual_values:
            score = compare_property_values(
                expected=expected,
                actual=actual,
            )

            best_score = max(best_score, score)

    return {
        "matched": best_score > 0,
        "score": best_score,
    }


def compare_property_values(
    expected: str,
    actual: str,
) -> int:
    """
    Generic value comparison for reconciliation detail properties.
    """

    expected_raw = str(expected or "").strip()
    actual_raw = str(actual or "").strip()

    if not expected_raw or not actual_raw:
        return 0

    expected_id = compact_identifier(expected_raw)
    actual_id = compact_identifier(actual_raw)

    # Exact URI/ID/code match
    if expected_id and actual_id and expected_id == actual_id:
        return 10

    expected_norm = normalize_text(expected_raw)
    actual_norm = normalize_text(actual_raw)

    # Exact normalized literal match
    if expected_norm == actual_norm:
        return 8

    # One contains the other
    if expected_norm in actual_norm or actual_norm in expected_norm:
        return 5

    # Token overlap
    overlap = token_overlap(expected_norm, actual_norm)

    if overlap >= 0.8:
        return 4

    if overlap >= 0.5:
        return 3

    return 0


def compact_identifier(value: str) -> str:
    """
    Converts values to comparable compact identifiers.

    Examples:
    https://d-nb.info/gnd/118540238 -> 118540238
    https://d-nb.info/standards/vocab/gnd/geographic-area-code#XA-DE -> XA-DE
    """

    value = str(value or "").strip()

    if value.startswith(GND_URI_PREFIX):
        return value.replace(GND_URI_PREFIX, "").strip("/")

    if value.startswith(GND_VOCAB_PREFIX):
        return value.split("#")[-1]

    if value.startswith("http://www.wikidata.org/entity/"):
        return value.rstrip("/").split("/")[-1]

    if value.startswith("https://www.wikidata.org/wiki/"):
        return value.rstrip("/").split("/")[-1]

    return value


def normalize_text(value: str) -> str:
    """
    Normalizes text for generic comparison.
    """

    value = str(value or "")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.lower()
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def token_overlap(left: str, right: str) -> float:
    """
    Calculates token overlap ratio.
    """

    left_tokens = set(re.findall(r"\w+", left))
    right_tokens = set(re.findall(r"\w+", right))

    if not left_tokens or not right_tokens:
        return 0.0

    overlap = left_tokens.intersection(right_tokens)

    return len(overlap) / max(len(left_tokens), len(right_tokens))


def flatten_value_to_strings(value: Any) -> list:
    """
    Converts OpenRefine values and indexed values into comparable strings.

    Supports:
    - plain literals
    - lists
    - dicts like {"id": "...", "name": "..."}
    - dicts like {"str": "..."}
    """

    if value is None:
        return []

    if isinstance(value, list):
        values: list[str] = []

        for item in value:
            values.extend(flatten_value_to_strings(item))

        return values

    if isinstance(value, dict):
        values: list[str] = []

        for key in ["id", "name", "label", "str", "value", "@id", "@value"]:
            if key in value and value[key] is not None:
                values.append(str(value[key]))

        if values:
            return values

        return [str(value)]

    return [str(value)]


def deduplicate(values: list[str]) -> list:
    """
    Deduplicates values while preserving order.
    """

    seen = set()
    result = []

    for value in values:
        if value in seen:
            continue

        seen.add(value)
        result.append(value)

    return result