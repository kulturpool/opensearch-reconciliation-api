"""
Constants and configuration data for the GND Reconciliation API.

This module contains type definitions, property lists, and other
static configuration used by the reconciliation service.
"""

GND_URI_PREFIX = "https://d-nb.info/gnd/"

BASE_URL = "http://127.0.0.1:8083"

GND_TYPES = [
    {
        "id": "AuthorityResource",
        "name": "Normdatenressource",
    },
    {
        "id": "CorporateBody",
        "name": "Körperschaft",
        "broader": [
            {
                "id": "AuthorityResource",
                "name": "Normdatenressource",
            }
        ],
    },
    {
        "id": "ConferenceOrEvent",
        "name": "Konferenz oder Veranstaltung",
        "broader": [
            {
                "id": "AuthorityResource",
                "name": "Normdatenressource",
            }
        ],
    },
    {
        "id": "SubjectHeading",
        "name": "Schlagwort",
        "broader": [
            {
                "id": "AuthorityResource",
                "name": "Normdatenressource",
            }
        ],
    },
    {
        "id": "Work",
        "name": "Werk",
        "broader": [
            {
                "id": "AuthorityResource",
                "name": "Normdatenressource",
            }
        ],
    },
    {
        "id": "PlaceOrGeographicName",
        "name": "Geografikum",
        "broader": [
            {
                "id": "AuthorityResource",
                "name": "Normdatenressource",
            }
        ],
    },
    {
        "id": "DifferentiatedPerson",
        "name": "Individualisierte Person",
        "broader": [
            {
                "id": "AuthorityResource",
                "name": "Normdatenressource",
            }
        ],
    },
    {
        "id": "Family",
        "name": "Familie",
        "broader": [
            {
                "id": "AuthorityResource",
                "name": "Normdatenressource",
            }
        ],
    },
]

GND_PROPERTIES = [
    {"id": "id", "name": "GND ID"},
    {"id": "uri", "name": "URI"},
    {"id": "preferredName", "name": "Preferred Name"},
    {"id": "variantName", "name": "Variant Names"},
    {"id": "type", "name": "Entity Type"},
    {"id": "dateOfBirth", "name": "Date of Birth"},
    {"id": "dateOfDeath", "name": "Date of Death"},
    {"id": "professionOrOccupation", "name": "Profession or Occupation"},
    {"id": "placeOfBirth", "name": "Place of Birth"},
    {"id": "placeOfDeath", "name": "Place of Death"},
    {"id": "source", "name": "Source"},
]

RELATION_PROPERTY_TYPES = {
    "affiliation": {
        "id": "CorporateBody",
        "name": "Corporate Body",
    },
    "professionOrOccupation": {
        "id": "SubjectHeading",
        "name": "Subject Heading",
    },
    "placeOfBirth": {
        "id": "PlaceOrGeographicName",
        "name": "Place or Geographic Name",
    },
    "placeOfDeath": {
        "id": "PlaceOrGeographicName",
        "name": "Place or Geographic Name",
    },
    "placeOfActivity": {
        "id": "PlaceOrGeographicName",
        "name": "Place or Geographic Name",
    },
    "familialRelationship": {
        "id": "Person",
        "name": "Person",
    },
    "relatedPerson": {
        "id": "Person",
        "name": "Person",
    },
    "relatedTerm": {
        "id": "SubjectHeading",
        "name": "Subject Heading",
    },
    "broaderTermGeneral": {
        "id": "SubjectHeading",
        "name": "Subject Heading",
    },
    "broaderTermInstantial": {
        "id": "SubjectHeading",
        "name": "Subject Heading",
    },
    "broaderTermPartitive": {
        "id": "SubjectHeading",
        "name": "Subject Heading",
    },
}
