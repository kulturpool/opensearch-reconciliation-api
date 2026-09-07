"""
Registry of enabled VocabConfig instances.

GND is always enabled. Getty vocabularies (Phase 4/5) will register
themselves here once api/vocabularies/getty.py exists, gated by
config.GETTY_VOCABULARIES.
"""

from api.vocabularies.base import VocabConfig
from api.vocabularies.gnd import GND_VOCAB

VOCABULARIES: dict[str, VocabConfig] = {
    GND_VOCAB.key: GND_VOCAB,
}


def get_vocab(key: str) -> VocabConfig:
    """
    Looks up a registered VocabConfig by key.

    Raises KeyError if the vocabulary isn't registered/enabled.
    """

    return VOCABULARIES[key]


def enabled_vocabularies() -> list[VocabConfig]:
    """
    Returns all currently registered/enabled VocabConfig instances.
    """

    return list(VOCABULARIES.values())
