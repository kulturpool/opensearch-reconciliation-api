"""
Shape test for the Getty AAT OpenRefine service manifest.

Unlike test_manifest_gnd.py, there is no golden byte-for-byte fixture for
Getty (it was never live-captured against a running service pre-refactor),
so this asserts the manifest's structural shape and Getty-specific values
instead: service URLs scoped under the /getty route prefix, AAT's identifier
space, and the AAT root type being present in defaultTypes.
"""

from api.reconciliation_utils import service_manifest_response
from api.vocabularies.getty import GETTY_VOCAB


def test_getty_manifest_shape():
    manifest = service_manifest_response(vocab=GETTY_VOCAB)

    assert manifest["versions"] == ["0.2"]
    assert manifest["name"] == "Local Getty AAT Reconciliation Service"
    assert manifest["identifierSpace"] == "http://vocab.getty.edu/aat/"
    assert manifest["schemaSpace"] == "http://vocab.getty.edu/aat/"

    # defaultTypes always includes the AAT root type first.
    default_types = manifest["defaultTypes"]
    assert default_types[0] == {
        "id": "aat",
        "name": "Getty Art & Architecture Thesaurus",
    }
    assert len(default_types) > 1

    # All service URLs are scoped under the /getty route prefix.
    assert "/getty" in manifest["preview"]["url"]
    assert manifest["suggest"]["entity"]["service_url"].endswith("/getty")
    assert manifest["suggest"]["type"]["service_url"].endswith("/getty")
    assert manifest["suggest"]["property"]["service_url"].endswith("/getty")
    assert manifest["extend"]["propose_properties"]["service_url"].endswith("/getty")


def test_getty_manifest_batch_size_matches_gnd():
    from api.vocabularies.gnd import GND_VOCAB

    getty_manifest = service_manifest_response(vocab=GETTY_VOCAB)
    gnd_manifest = service_manifest_response(vocab=GND_VOCAB)

    assert getty_manifest["batchSize"] == gnd_manifest["batchSize"] == 50
