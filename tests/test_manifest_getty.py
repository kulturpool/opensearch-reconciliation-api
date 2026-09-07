"""
Shape test for the Getty AAT OpenRefine service manifest.

Unlike test_manifest_gnd.py, there is no golden byte-for-byte fixture for
Getty (it was never live-captured against a running service pre-refactor),
so this asserts the manifest's structural shape and Getty-specific values
instead: service URLs scoped under the /aat route prefix, AAT's identifier
space, and the AAT root type being present in defaultTypes.
"""

from api.reconciliation_utils import service_manifest_response
from api.vocabularies.getty import AAT_VOCAB, GETTY_VOCAB


def test_getty_manifest_shape():
    manifest = service_manifest_response(vocab=AAT_VOCAB)

    assert manifest["versions"] == ["0.2"]
    assert manifest["name"] == "AAT search"
    assert manifest["identifierSpace"] == "http://vocab.getty.edu/aat/"
    assert manifest["schemaSpace"] == "http://vocab.getty.edu/aat/"
    assert manifest["view"]["url"] == "http://vocab.getty.edu/page/{{id}}"

    # defaultTypes always includes the AAT root type first.
    default_types = manifest["defaultTypes"]
    assert default_types[0] == {"id": "aat", "name": "Getty Art & Architecture Thesaurus"}
    assert any(item.get("id") == "aat:Concept" for item in default_types)
    assert len(default_types) > 1

    # All service URLs are scoped under the /aat route prefix.
    assert "/aat" in manifest["preview"]["url"]
    assert manifest["suggest"]["entity"]["service_url"].endswith("/aat")
    assert manifest["suggest"]["type"]["service_url"].endswith("/aat")
    assert manifest["suggest"]["property"]["service_url"].endswith("/aat")
    assert manifest["extend"]["propose_properties"]["service_url"].endswith("/aat")


def test_getty_manifest_batch_size_matches_gnd():
    from api.vocabularies.gnd import GND_VOCAB

    getty_manifest = service_manifest_response(vocab=AAT_VOCAB)
    gnd_manifest = service_manifest_response(vocab=GND_VOCAB)

    assert getty_manifest["batchSize"] == gnd_manifest["batchSize"] == 50


def test_combined_getty_manifest_exposes_only_high_level_types():
    manifest = service_manifest_response(vocab=GETTY_VOCAB)

    assert manifest["name"] == "Getty search"
    assert manifest["suggest"]["type"]["service_url"].endswith("/getty")

    default_types = manifest["defaultTypes"]
    type_ids = [item["id"] for item in default_types]
    type_names = {item["id"]: item["name"] for item in default_types}

    assert type_ids == ["getty", "aat", "ulan", "tgn"]
    assert type_names == {
        "getty": "Search all Vocabs",
        "aat": "AAT search",
        "ulan": "ULAN search",
        "tgn": "TGN search",
    }
