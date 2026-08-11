import json
from pathlib import Path

GND_VOCAB_PREFIX = "https://d-nb.info/standards/vocab/gnd/"
VOCAB_LABELS_PATH = Path("config/gnd_vocab_labels.json")


_vocab_labels_cache: dict[str, str] | None = None


def load_vocab_labels() -> dict[str, str]:
    global _vocab_labels_cache

    if _vocab_labels_cache is not None:
        return _vocab_labels_cache

    if not VOCAB_LABELS_PATH.exists():
        _vocab_labels_cache = {}
        return _vocab_labels_cache

    with VOCAB_LABELS_PATH.open("r", encoding="utf-8") as file:
        _vocab_labels_cache = json.load(file)

    return _vocab_labels_cache


def resolve_gnd_vocab_uri(value: str) -> str | None:
    """
    Resolves GND vocabulary URIs to readable labels.

    Example:
    https://d-nb.info/standards/vocab/gnd/geographic-area-code#XA-BE
    -> Belgien (XA-BE)
    """

    if not value.startswith(GND_VOCAB_PREFIX):
        return None

    compact_id = value.replace(GND_VOCAB_PREFIX, "")

    if not compact_id:
        return None

    labels = load_vocab_labels()

    label = labels.get(compact_id)
    code = compact_id.split("#")[-1]

    if label:
        return f"{label} ({code})"

    # Fallback: if no label is known, at least return the compact code.
    return code
