"""
Constants and configuration data for the GND Reconciliation API.

This module contains type definitions, property lists, and other
static configuration used by the reconciliation service.
"""

from config import GND_URI_PREFIX, PUBLIC_BASE_URL

BASE_URL = PUBLIC_BASE_URL

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

