"""
GND entity type definitions and mappings.

This module contains domain knowledge about GND (Gemeinsame Normdatei)
entity types, their hierarchies, labels, and aliases.
"""

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
    "AuthorityResource": {
        "name": "Authority Resource",
    },
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
