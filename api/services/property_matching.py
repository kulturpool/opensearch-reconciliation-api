import re
import unicodedata
from typing import Any

from config import GND_URI_PREFIX

GND_VOCAB_PREFIX = "https://d-nb.info/standards/vocab/gnd/"


def calculate_property_bonus(
    source: dict[str, Any],
    requested_properties: list[dict[str, Any]],
    max_bonus: int = 20,
    max_penalty: int = 15,
) -> tuple[int, int, list[dict[str, Any]]]:
    """
    Calculates a generic score bonus and penalty from OpenRefine detail columns.

    Works for all properties, not only person-related fields.

    Bonus: When property values match
    Penalty: When property is requested, candidate HAS the property, but values don't match
    No penalty: When candidate doesn't have the property at all

    Returns:
    - bonus score
    - penalty score (positive number to subtract)
    - feature list for debugging
    """

    if not requested_properties:
        return 0, 0, []

    total_bonus = 0
    total_penalty = 0
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

        if match_result["matched"]:
            # Property matches - add bonus
            total_bonus += match_result["score"]
        elif actual_values:
            # Property requested, candidate HAS it, but doesn't match - penalty
            # Scale penalty based on how important the property is
            # Date fields get higher penalty since they're very discriminating
            penalty = calculate_mismatch_penalty(prop_id, match_result["score"])
            total_penalty += penalty

            features.append(
                {
                    "id": f"property_mismatch_penalty_{prop_id}",
                    "value": penalty,
                }
            )

    return min(total_bonus, max_bonus), min(total_penalty, max_penalty), features


def calculate_mismatch_penalty(prop_id: str, match_score: int) -> int:
    """
    Calculates penalty for property mismatch based on property type.

    Date fields and identifiers are more discriminating, so higher penalty.
    Penalties are intentionally moderate: GND properties (especially dates)
    can be fuzzy/approximate, so a mismatch shouldn't overwhelm otherwise
    strong name evidence.

    Note: dateOfBirth/dateOfDeath/dateOfBirthAndDeath are scored separately
    via dedicated logic in api.services.search.score_date_signals and are
    excluded before reaching this generic path.
    """
    # High-penalty fields: dates and identifiers
    high_penalty_fields = [
        "dateOfEstablishment",
        "dateOfTermination",
        "dateOfPublication",
        "dateOfProduction",
        "dateOfConferenceOrEvent",
        "id",
        "gndIdentifier",
    ]

    # Medium-penalty fields: places and specific attributes
    medium_penalty_fields = [
        "placeOfBirth",
        "placeOfDeath",
        "placeOfBusiness",
        "placeOfActivity",
        "gender",
    ]

    if prop_id in high_penalty_fields:
        return 6  # Strong, but not overwhelming, penalty for date/ID mismatch
    elif prop_id in medium_penalty_fields:
        return 4  # Moderate penalty
    else:
        return 2  # Small penalty for other fields


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
    - shared year between date-like values (e.g. "1749" vs "1749-08-28"): 7
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

    # Date-aware comparison: values like "1749" and "1749-08-28" refer to the
    # same date at different precision (e.g. a spreadsheet column only has the
    # birth year, while the index stores the full date). Treat overlapping
    # years as a match instead of falling through to plain substring/token
    # comparison, which would either miss the match (year not a full-string
    # containment of a "DD.MM.YYYY" formatted date) or, conversely, wrongly
    # give partial credit to unrelated dates that happen to share digits.
    date_score = compare_date_like_values(expected_raw, actual_raw)

    if date_score is not None:
        return date_score

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


DATE_APPROXIMATION_WORDS_RE = re.compile(
    r"\b(ca|circa|approx|approximately|um|vor|nach|before|after)\b\.?",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"(?<!\d)\d{3,4}(?!\d)")


def looks_date_like(value: str) -> bool:
    """
    Heuristically checks whether a value represents a date (possibly with
    reduced precision, ranges, or approximation markers), regardless of the
    property it came from.

    Examples that should be considered date-like:
    - "1749"
    - "1749-08-28"
    - "28.08.1749"
    - "1749-1832" (range)
    - "ca. 1749", "vor 1749"

    Plain text (names, places, etc.) will not match this pattern.
    """

    cleaned = DATE_APPROXIMATION_WORDS_RE.sub("", value.lower())
    cleaned = cleaned.replace("?", "").strip()

    if not cleaned:
        return False

    return bool(re.fullmatch(r"[\d\-./\s]+", cleaned)) and bool(YEAR_RE.search(cleaned))


def compare_date_like_values(expected: str, actual: str) -> int | None:
    """
    Compares two values as dates when both look date-like.

    Returns:
    - a score (>0) when at least one year is shared between both values,
      e.g. a requested birth year matches within a full birth date
    - 0 when both values are dates but share no common year (a genuine
      mismatch, e.g. different birth years)
    - None when the values aren't both date-like, so the caller should fall
      back to the generic text comparison instead
    """

    if not looks_date_like(expected) or not looks_date_like(actual):
        return None

    expected_years = set(YEAR_RE.findall(expected))
    actual_years = set(YEAR_RE.findall(actual))

    if not expected_years or not actual_years:
        return None

    if expected_years & actual_years:
        # Shared year, e.g. "1749" vs "1749-08-28" - treat as a solid match
        # even though precision differs.
        return 7

    # Off-by-one year: common transcription/approximation fuzziness (e.g.
    # differing calendar conventions or slightly wrong source data).
    # Give a little credit instead of treating it as a hard mismatch.
    for expected_year in expected_years:
        for actual_year in actual_years:
            try:
                if abs(int(expected_year) - int(actual_year)) <= 1:
                    return 3
            except ValueError:
                continue

    # Both are dates, with clearly different years - a real mismatch.
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
