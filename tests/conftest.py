"""
Shared pytest fixtures for GND characterization tests.

These fixtures capture representative OpenSearch source documents in the
shape produced by importer/normalize_gnd_lds.py + importer/normalize_entityfacts.py
(see api/services/search.py RECONCILIATION_SOURCE_FIELDS), so scoring/matching
tests can run without a live OpenSearch instance.
"""

import pytest


@pytest.fixture
def goethe_record() -> dict:
    """A DifferentiatedPerson record, modeled on GND 118540238."""
    return {
        "id": "118540238",
        "uri": "https://d-nb.info/gnd/118540238",
        "preferredName": "Goethe, Johann Wolfgang von",
        "variantName": ["Goethe, Johann W.", "Johann Wolfgang von Goethe"],
        "type": ["DifferentiatedPerson"],
        "dateOfBirth": "1749-08-28",
        "dateOfDeath": "1832-03-22",
        "professionOrOccupation": ["Schriftsteller", "Naturforscher"],
        "placeOfBirth": ["Frankfurt am Main"],
        "placeOfDeath": ["Weimar"],
        "source": "dnb-gnd-lds",
        "availableProperties": [
            "dateOfBirth",
            "dateOfDeath",
            "professionOrOccupation",
            "placeOfBirth",
            "placeOfDeath",
        ],
        "propertiesFlat": [
            {"id": "academicDegree", "value": "Dr."},
        ],
    }


@pytest.fixture
def berlin_record() -> dict:
    """A PlaceOrGeographicName record."""
    return {
        "id": "4005728-8",
        "uri": "https://d-nb.info/gnd/4005728-8",
        "preferredName": "Berlin",
        "variantName": ["Berlin (Deutschland)"],
        "type": ["PlaceOrGeographicName"],
        "source": "dnb-gnd-lds",
        "availableProperties": [],
        "propertiesFlat": [],
    }
