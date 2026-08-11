"""
Fixed generic preview helpers for the local GND Reconciliation API.

Copy the relevant functions into: api/services/preview.py

Important:
- This file intentionally uses real HTML tags such as <a>, <div>, <img>.
- Do NOT replace them with escaped forms such as &lt;a&gt; or &lt;div&gt;.
"""

import json
from datetime import datetime
from html import escape
from typing import Any
from urllib.parse import unquote

from api.services.properties import get_property_values_from_record
from api.services.property_labels import property_label
from api.services.search import GND_TYPE_ALIASES, get_gnd_record_by_id
from api.services.vocab_resolver import resolve_gnd_vocab_uri
from config import DATA_DIR

GND_URI_PREFIX = "https://d-nb.info/gnd/"


BASE_PREVIEW_FIELDS = [
    "preferredName",
    "variantName",
    "type",
    "gndIdentifier",
    "uri",
    "sameAs",
]


TYPE_PREVIEW_FIELDS = {
    "Person": [
        "dateOfBirth",
        "dateOfDeath",
        "dateOfBirthAndDeath",
        "placeOfBirth",
        "placeOfBirthAsLiteral",
        "placeOfDeath",
        "placeOfDeathAsLiteral",
        "professionOrOccupation",
        "academicDegree",
        "nobilityTitle",
        "affiliation",
        "gender",
        "geographicAreaCode",
        "biographicalOrHistoricalInformation",
        "periodOfActivity",
        "fieldOfActivity",
        "publication",
    ],
    "CorporateBody": [
        "dateOfEstablishment",
        "dateOfTermination",
        "placeOfBusiness",
        "placeOfBusinessAsLiteral",
        "placeOfActivity",
        "geographicAreaCode",
        "fieldOfActivity",
        "precedingCorporateBody",
        "succeedingCorporateBody",
        "hierarchicalSuperiorOfTheCorporateBody",
        "homepage",
        "page",
    ],
    "ConferenceOrEvent": [
        "dateOfConferenceOrEvent",
        "placeOfConferenceOrEvent",
        "placeOfConferenceOrEventAsLiteral",
        "geographicAreaCode",
        "relatedCorporateBody",
        "relatedPerson",
        "precedingConferenceOrEvent",
        "succeedingConferenceOrEvent",
    ],
    "PlaceOrGeographicName": [
        "geographicAreaCode",
        "broaderTermGeneral",
        "broaderTermPartitive",
        "relatedPlaceOrGeographicName",
        "coordinates",
        "preferredNameForThePlaceOrGeographicName",
        "variantNameForThePlaceOrGeographicName",
    ],
    "SubjectHeading": [
        "broaderTermGeneral",
        "broaderTermInstantial",
        "broaderTermPartitive",
        "relatedTerm",
        "relatedDdcWithDegreeOfDeterminacy1",
        "relatedDdcWithDegreeOfDeterminacy2",
        "relatedDdcWithDegreeOfDeterminacy3",
        "gndSubjectCategory",
        "usingInstructions",
    ],
    "Work": [
        "firstAuthor",
        "author",
        "composer",
        "creator",
        "dateOfPublication",
        "dateOfProduction",
        "formOfWorkAndExpression",
        "mediumOfPerformance",
        "opusNumericDesignationOfMusicalWork",
        "thematicIndexNumericDesignationOfMusicalWork",
        "relatedWork",
        "relatedPerson",
        "relatedCorporateBody",
    ],
}


FALLBACK_PREVIEW_FIELDS = [
    "biographicalOrHistoricalInformation",
    "geographicAreaCode",
    "professionOrOccupation",
    "affiliation",
    "placeOfActivity",
    "publication",
    "relatedTerm",
    "relatedPerson",
    "relatedWork",
    "homepage",
    "page",
]


PREVIEW_IMAGE_FIELDS = [
    "image",
    "thumbnail",
    "depiction",
    "foafDepiction",
    "schemaImage",
]


def get_last_update_date() -> str | None:
    """
    Reads the last successful update date from update_state.json.
    Returns a formatted German date string or None if unavailable.
    """
    update_state_file = DATA_DIR / "state" / "update_state.json"

    try:
        if not update_state_file.exists():
            return None

        with open(update_state_file, "r", encoding="utf-8") as f:
            state = json.load(f)

        last_update = state.get("last_successful_update")
        if not last_update:
            return None

        # Parse ISO format date
        dt = datetime.fromisoformat(last_update.replace("Z", "+00:00"))

        # Format as German date: "11. August 2026"
        months_de = [
            "Januar",
            "Februar",
            "März",
            "April",
            "Mai",
            "Juni",
            "Juli",
            "August",
            "September",
            "Oktober",
            "November",
            "Dezember",
        ]
        return f"{dt.day}. {months_de[dt.month - 1]} {dt.year}"

    except (OSError, json.JSONDecodeError, ValueError, KeyError, IndexError):
        return None


def render_preview_for_id(gnd_id: str) -> tuple[str, int]:
    """
    Builds preview HTML and HTTP status for a GND identifier.

    Supports:
    - plain GND IDs, e.g. 118540238
    - GND URIs, e.g. https://d-nb.info/gnd/118540238
    - URL-encoded variants
    """

    normalized_id = normalize_preview_id(gnd_id)
    record = get_gnd_record_by_id(normalized_id)

    if record is None:
        return render_not_found_preview(normalized_id), 404

    return render_gnd_preview(record), 200


def normalize_preview_id(value: str) -> str:
    """
    Normalizes preview identifiers.
    """

    value = unquote(str(value)).strip()

    if value.startswith(GND_URI_PREFIX):
        value = value.replace(GND_URI_PREFIX, "").strip("/")

    return value


def render_not_found_preview(gnd_id: str) -> str:
    """
    Renders a small not-found preview.
    """

    return f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
  </head>
  <body style="font-family: sans-serif; padding: 12px;">
    <h3>GND record not found</h3>
    <p>No record found for GND ID: <code>{escape(gnd_id)}</code></p>
  </body>
</html>
"""


def render_gnd_preview(record: dict[str, Any]) -> str:
    """
    Renders a type-aware but generic HTML preview for OpenRefine.
    """

    gnd_id = str(record.get("id", ""))
    name = str(record.get("preferredName", ""))
    uri = str(record.get("uri") or f"{GND_URI_PREFIX}{gnd_id}")

    broad_type = get_record_broad_type(record)
    image_url = get_preview_image_url(record)
    image_html = build_image_html(image_url)

    field_rows = []
    preview_fields = get_preview_fields_for_record(record)

    for prop_id in preview_fields:
        value = get_property_values_from_record(record, prop_id)

        formatted_value = format_preview_values(
            prop_id=prop_id,
            value=value,
        )

        if not formatted_value:
            continue

        label = property_label(prop_id)

        field_rows.append(
            f"""
            <div class="row">
              <div class="label">{escape(label)}</div>
              <div class="value">{formatted_value}</div>
            </div>
            """
        )

    fields_html = "\n".join(field_rows)

    type_badge = ""

    if broad_type:
        type_badge = f'<span class="type-badge">{escape(broad_type)}</span>'

    # Get last update date
    last_update = get_last_update_date()
    update_footer = ""
    if last_update:
        update_footer = f'<div class="update-footer">Letzte Aktualisierung der Daten: {escape(last_update)}</div>'

    return f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <style>
      body {{
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        font-size: 13px;
        line-height: 1.4;
        margin: 0;
        padding: 12px;
        color: #222;
        background: #fff;
      }}

      .preview {{
        display: flex;
        gap: 12px;
        align-items: flex-start;
      }}

      .image-box {{
        flex: 0 0 auto;
        width: 90px;
        max-height: 120px;
        overflow: hidden;
        border-radius: 6px;
        border: 1px solid #ddd;
        background: #f7f7f7;
      }}

      .image-box img {{
        width: 100%;
        height: auto;
        display: block;
      }}

      .content {{
        flex: 1 1 auto;
        min-width: 0;
      }}

      h3 {{
        margin: 0 0 5px 0;
        font-size: 15px;
      }}

      .meta {{
        color: #666;
        margin-bottom: 8px;
      }}

      .type-badge {{
        display: inline-block;
        margin-left: 6px;
        padding: 1px 6px;
        border-radius: 999px;
        background: #eef3ff;
        color: #245;
        font-size: 11px;
      }}

      .row {{
        display: grid;
        grid-template-columns: 130px 1fr;
        gap: 8px;
        margin: 3px 0;
      }}

      .label {{
        color: #555;
        font-weight: 600;
      }}

      .value {{
        color: #222;
        word-break: break-word;
      }}

      a {{
        color: #0645ad;
        text-decoration: none;
      }}

      a:hover {{
        text-decoration: underline;
      }}

      .update-footer {{
        margin-top: 12px;
        padding-top: 8px;
        border-top: 1px solid #eee;
        color: #888;
        font-size: 11px;
        text-align: right;
      }}
    </style>
  </head>
  <body>
    <div class="preview">
      {image_html}
      <div class="content">
        <h3>{escape(name)} {type_badge}</h3>
        <div class="meta">
          {make_html_link(uri, "GND " + gnd_id)}
        </div>
        {fields_html}
        {update_footer}
      </div>
    </div>
  </body>
</html>
"""


def get_record_broad_type(record: dict[str, Any]) -> str | None:
    """
    Determines the broad preview type from record type.
    """

    broad_type = record.get("broadType")

    if isinstance(broad_type, str) and broad_type:
        return broad_type

    record_types = record.get("type", [])

    if isinstance(record_types, str):
        record_types = [record_types]

    if not isinstance(record_types, list):
        return None

    broad_type_order = [
        "Person",
        "CorporateBody",
        "ConferenceOrEvent",
        "PlaceOrGeographicName",
        "SubjectHeading",
        "Work",
    ]

    for candidate_broad_type in broad_type_order:
        allowed_types = GND_TYPE_ALIASES.get(
            candidate_broad_type,
            [candidate_broad_type],
        )

        for record_type in record_types:
            if record_type in allowed_types:
                return candidate_broad_type

    return None


def get_preview_fields_for_record(record: dict[str, Any]) -> list[str]:
    """
    Builds a preview field list based on broad entity type.
    """

    fields = list(BASE_PREVIEW_FIELDS)

    broad_type = get_record_broad_type(record)

    if broad_type and broad_type in TYPE_PREVIEW_FIELDS:
        fields.extend(TYPE_PREVIEW_FIELDS[broad_type])

    fields.extend(FALLBACK_PREVIEW_FIELDS)

    return deduplicate_preview_fields(fields)


def deduplicate_preview_fields(fields: list[str]) -> list[str]:
    """
    Deduplicates preview fields while preserving order.
    """

    seen = set()
    result = []

    for field in fields:
        if field in seen:
            continue

        seen.add(field)
        result.append(field)

    return result


def get_preview_image_url(record: dict[str, Any]) -> str | None:
    """
    Returns an image URL for the preview if available.
    """

    for prop_id in PREVIEW_IMAGE_FIELDS:
        value = get_property_values_from_record(record, prop_id)
        image_url = first_image_url(value)

        if image_url:
            return image_url

    return None


def first_image_url(value: Any) -> str | None:
    """
    Extracts the first likely image URL from scalar/list/dict values.
    """

    if value is None:
        return None

    if isinstance(value, list):
        for item in value:
            found = first_image_url(item)

            if found:
                return found

        return None

    if isinstance(value, dict):
        for key in ["id", "@id", "url", "value", "str", "name"]:
            if key in value:
                found = first_image_url(value[key])

                if found:
                    return found

        return None

    value_string = str(value).strip()

    if not value_string.startswith(("http://", "https://")):
        return None

    lower = value_string.lower()

    image_extensions = [
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".svg",
    ]

    if any(lower.endswith(extension) for extension in image_extensions):
        return value_string

    if "commons.wikimedia.org/wiki/special:filepath/" in lower:
        return value_string

    return None


def build_image_html(image_url: str | None) -> str:
    """
    Builds preview image HTML if an image URL is available.
    """

    if not image_url:
        return ""

    safe_image_url = escape(str(image_url), quote=True)

    return f'<div class="image-box"><img src="{safe_image_url}" alt="" /></div>'


def format_preview_values(prop_id: str, value: Any) -> str:
    """
    Formats a property value for HTML preview.
    """

    if value is None:
        return ""

    if isinstance(value, list):
        parts = []

        for item in value:
            formatted = format_preview_values(prop_id, item)

            if formatted:
                parts.append(formatted)

        return ", ".join(parts)

    if isinstance(value, dict):
        value = (
            value.get("name")
            or value.get("label")
            or value.get("str")
            or value.get("value")
            or value.get("id")
            or value.get("@id")
            or value.get("@value")
        )

        if value is None:
            return ""

    value_string = str(value).strip()

    if not value_string:
        return ""

    resolved = resolve_preview_value(value_string)

    if resolved:
        if value_string.startswith(("http://", "https://")):
            return make_html_link(
                href=value_string,
                label=resolved,
            )

        return escape(resolved)

    if value_string.startswith(("http://", "https://")):
        return make_html_link(
            href=value_string,
            label=value_string,
        )

    return escape(value_string)


def resolve_preview_value(value: str) -> str | None:
    """
    Resolves preview values for display.
    """

    resolved_gnd_entity = resolve_gnd_uri_to_label(value)

    if resolved_gnd_entity:
        return resolved_gnd_entity

    resolved_vocab_value = resolve_gnd_vocab_uri(value)

    if resolved_vocab_value:
        return resolved_vocab_value

    return None


def resolve_gnd_uri_to_label(value: str) -> str | None:
    """
    Resolves normal GND entity URIs to preferredName.
    """

    if not value.startswith(GND_URI_PREFIX):
        return None

    gnd_id = value.replace(GND_URI_PREFIX, "").strip("/")

    if not gnd_id:
        return None

    record = get_gnd_record_by_id(gnd_id)

    if not record:
        return None

    preferred_name = record.get("preferredName")

    if not preferred_name:
        return None

    return f"{preferred_name} ({gnd_id})"


def make_html_link(href: str, label: str) -> str:
    """
    Builds a safe HTML link.
    """

    safe_href = escape(str(href), quote=True)
    safe_label = escape(str(label))

    return f'<a href="{safe_href}" target="_blank" rel="noopener noreferrer">{safe_label}</a>'
