"""
GND_VOCAB: the VocabConfig instance describing the (default, always-on) GND
vocabulary. Values are migrated verbatim from api/constants.py, api/gnd_types.py,
and the various api/services/*.py modules - see the module docstrings there
for provenance of each constant.
"""

from pathlib import Path

from api.constants import GND_TYPES
from api.gnd_types import AUTHORITY_RESOURCE_TYPE, GND_TYPE_ALIASES, GND_TYPE_LABELS
from config import GND_URI_PREFIX, PUBLIC_BASE_URL

# Reconciliation API 0.2 defines `schemaSpace` as a URI identifying the *type*
# of the entities returned - a different concept from `identifierSpace` (the
# namespace of the entity identifiers). For GND this is the GND ontology's
# AuthorityResource class, which every GND entity is an instance of.
GND_SCHEMA_SPACE = "https://d-nb.info/standards/elementset/gnd#AuthorityResource"

# Fields returned from OpenSearch during reconciliation. See
# api/services/search.py RECONCILIATION_SOURCE_FIELDS for rationale.
GND_SOURCE_FIELDS = (
    "id",
    "uri",
    "preferredName",
    "variantName",
    "type",
    "dateOfBirth",
    "dateOfDeath",
    "dateOfBirthAndDeath",
    "professionOrOccupation",
    "placeOfBirth",
    "placeOfDeath",
    "propertiesFlat",
)

GND_DATE_PROPERTY_IDS = frozenset({"dateOfBirth", "dateOfDeath", "dateOfBirthAndDeath"})

GND_RELIABLE_TOP_LEVEL_PROPERTY_IDS = GND_DATE_PROPERTY_IDS | frozenset(
    {"professionOrOccupation", "placeOfBirth", "placeOfDeath"}
)

GND_KEYWORD_FIELD_PROPERTY_IDS = {
    "id": "id",
    "gndIdentifier": "id",
    "uri": "uri",
}

GND_HIGH_PRIORITY_PROPERTY_IDS = frozenset(
    {
        "dateOfBirth",
        "dateOfDeath",
        "dateOfBirthAndDeath",
        "dateOfEstablishment",
        "dateOfTermination",
        "dateOfPublication",
        "dateOfProduction",
        "dateOfConferenceOrEvent",
        "id",
        "gndIdentifier",
        "uri",
    }
)

GND_MEDIUM_PRIORITY_PROPERTY_IDS = frozenset(
    {
        "placeOfBirth",
        "placeOfDeath",
        "placeOfBusiness",
        "placeOfActivity",
        "gender",
    }
)

GND_MULTI_MATCH_FIELDS = ("preferredName^5", "variantName^3", "id^10")

GND_FUZZY_FIELDS = (
    "preferredName^4",
    "variantName^3",
    "professionOrOccupation^2",
    "placeOfBirth",
    "placeOfDeath",
    "id^5",
)

GND_SELF_IDENTIFIER_PROPERTY_IDS = frozenset({"id", "uri", "gndIdentifier"})

# Full relation-property -> reconciled-entity-type map used by the /extend
# endpoint. This is the single canonical copy (api/constants.py used to hold
# a stale, incomplete duplicate of this - removed, see repo memory).
GND_RELATION_PROPERTY_TYPES = {
    "affiliation": {"id": "CorporateBody", "name": "Corporate Body"},
    "professionOrOccupation": {"id": "SubjectHeading", "name": "Subject Heading"},
    "placeOfBirth": {"id": "PlaceOrGeographicName", "name": "Place or Geographic Name"},
    "placeOfDeath": {"id": "PlaceOrGeographicName", "name": "Place or Geographic Name"},
    "placeOfActivity": {
        "id": "PlaceOrGeographicName",
        "name": "Place or Geographic Name",
    },
    "familialRelationship": {"id": "Person", "name": "Person"},
    "relatedPerson": {"id": "Person", "name": "Person"},
    "relatedTerm": {"id": "SubjectHeading", "name": "Subject Heading"},
    "broaderTermGeneral": {"id": "SubjectHeading", "name": "Subject Heading"},
    "broaderTermInstantial": {"id": "SubjectHeading", "name": "Subject Heading"},
    "broaderTermPartitive": {"id": "SubjectHeading", "name": "Subject Heading"},
    "isPartOf": {"id": "AuthorityResource", "name": "Normdatenressource"},
    "successor": {"id": "AuthorityResource", "name": "Normdatenressource"},
    "predecessor": {"id": "AuthorityResource", "name": "Normdatenressource"},
    "founder": {"id": "Person", "name": "Person"},
    "topic": {"id": "SubjectHeading", "name": "Subject Heading"},
    "isA": {"id": "SubjectHeading", "name": "Subject Heading"},
    "associatedPlace": {
        "id": "PlaceOrGeographicName",
        "name": "Place or Geographic Name",
    },
    "placeOfEvent": {"id": "PlaceOrGeographicName", "name": "Place or Geographic Name"},
    "organizerOrHost": {"id": "CorporateBody", "name": "Corporate Body"},
}

GND_BASE_PREVIEW_FIELDS = (
    "preferredName",
    "variantName",
    "type",
    "gndIdentifier",
    "uri",
    "sameAs",
)

GND_TYPE_PREVIEW_FIELDS = {
    "Person": (
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
    ),
    "CorporateBody": (
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
    ),
    "ConferenceOrEvent": (
        "dateOfConferenceOrEvent",
        "placeOfConferenceOrEvent",
        "placeOfConferenceOrEventAsLiteral",
        "geographicAreaCode",
        "relatedCorporateBody",
        "relatedPerson",
        "precedingConferenceOrEvent",
        "succeedingConferenceOrEvent",
    ),
    "PlaceOrGeographicName": (
        "geographicAreaCode",
        "broaderTermGeneral",
        "broaderTermPartitive",
        "relatedPlaceOrGeographicName",
        "coordinates",
        "preferredNameForThePlaceOrGeographicName",
        "variantNameForThePlaceOrGeographicName",
    ),
    "SubjectHeading": (
        "broaderTermGeneral",
        "broaderTermInstantial",
        "broaderTermPartitive",
        "relatedTerm",
        "relatedDdcWithDegreeOfDeterminacy1",
        "relatedDdcWithDegreeOfDeterminacy2",
        "relatedDdcWithDegreeOfDeterminacy3",
        "gndSubjectCategory",
        "usingInstructions",
    ),
    "Work": (
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
    ),
}

GND_FALLBACK_PREVIEW_FIELDS = (
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
)

GND_PREVIEW_IMAGE_FIELDS = ("image", "thumbnail", "depiction", "foafDepiction", "schemaImage")

# Sourced from api.services.property_labels (the pre-existing canonical
# home for GND's curated German property labels) rather than duplicated
# here, to avoid two copies drifting apart.
from api.services.property_labels import PROPERTY_LABEL_OVERRIDES as GND_PROPERTY_LABEL_OVERRIDES  # noqa: E402


def normalize_gnd_identifier(value: str) -> str:
    """
    Strips the GND URI prefix from a value, if present.

    "https://d-nb.info/gnd/118540238" -> "118540238"
    "118540238" -> "118540238"
    """

    value = str(value or "").strip()

    if value.startswith(GND_URI_PREFIX):
        return value.replace(GND_URI_PREFIX, "").strip("/")

    return value


# Imported lazily inside the factory function to avoid a hard import-order
# dependency between this module and config/__init__.py's INDEX_NAME.
def _build_gnd_vocab():
    from config import INDEX_NAME

    from api.vocabularies.base import VocabConfig

    return VocabConfig(
        key="gnd",
        service_name="OpenSearch Reconciliation API for GND",
        index_name=INDEX_NAME,
        identifier_space=GND_URI_PREFIX,
        schema_space=GND_SCHEMA_SPACE,
        view_url_template=f"{GND_URI_PREFIX}{{{{id}}}}",
        uri_prefix=GND_URI_PREFIX,
        normalize_identifier=normalize_gnd_identifier,
        types=tuple(GND_TYPES),
        type_labels=GND_TYPE_LABELS,
        type_aliases=GND_TYPE_ALIASES,
        root_type=AUTHORITY_RESOURCE_TYPE,
        source_fields=GND_SOURCE_FIELDS,
        date_property_ids=GND_DATE_PROPERTY_IDS,
        reliable_top_level_property_ids=GND_RELIABLE_TOP_LEVEL_PROPERTY_IDS,
        keyword_field_property_ids=GND_KEYWORD_FIELD_PROPERTY_IDS,
        high_priority_property_ids=GND_HIGH_PRIORITY_PROPERTY_IDS,
        medium_priority_property_ids=GND_MEDIUM_PRIORITY_PROPERTY_IDS,
        id_boost=20.0,
        preferred_keyword_boost=15.0,
        preferred_phrase_boost=12.0,
        variant_keyword_boost=10.0,
        variant_phrase_boost=8.0,
        multi_match_fields=GND_MULTI_MATCH_FIELDS,
        multi_match_boost=5.0,
        fuzzy_fields=GND_FUZZY_FIELDS,
        fuzzy_max_expansions=20,
        fuzzy_max_terms=6,
        uses_date_signals=True,
        relation_property_types=GND_RELATION_PROPERTY_TYPES,
        self_identifier_property_ids=GND_SELF_IDENTIFIER_PROPERTY_IDS,
        preview_base_fields=GND_BASE_PREVIEW_FIELDS,
        preview_type_fields=GND_TYPE_PREVIEW_FIELDS,
        preview_fallback_fields=GND_FALLBACK_PREVIEW_FIELDS,
        preview_image_fields=GND_PREVIEW_IMAGE_FIELDS,
        property_registry_path=Path("config/gnd_properties.json"),
        property_label_overrides=GND_PROPERTY_LABEL_OVERRIDES,
        vocab_labels_path=Path("config/gnd_vocab_labels.json"),
    )


GND_VOCAB = _build_gnd_vocab()

# Kept for the BASE_URL previously hardcoded in api/constants.py.
GND_BASE_URL = PUBLIC_BASE_URL

