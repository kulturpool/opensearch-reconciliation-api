"""
Characterization test for the OpenRefine service manifest.

Compares api.reconciliation_utils.service_manifest_response() byte-for-byte
against the golden fixture captured from the live (pre-refactor) service in
tests/fixtures/golden/manifest.json.
"""

import json
from pathlib import Path

from api.reconciliation_utils import service_manifest_response

GOLDEN_DIR = Path(__file__).parent / "fixtures" / "golden"


def test_manifest_matches_golden_fixture():
    expected = json.loads((GOLDEN_DIR / "manifest.json").read_text())
    actual = service_manifest_response()
    assert actual == expected
