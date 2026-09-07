import json
from pathlib import Path

GND_VOCAB_PREFIX = "https://d-nb.info/standards/vocab/gnd/"
# Kept for backward compatibility with existing imports; GND_VOCAB.vocab_
# labels_path (see api/vocabularies/gnd.py) is now the single source of
# truth for the GND vocab labels file location.
VOCAB_LABELS_PATH = Path("config/gnd_vocab_labels.json")


_vocab_labels_cache: dict[str, dict[str, str]] = {}


def load_vocab_labels(vocab_labels_path: Path | None = None) -> dict[str, str]:
    vocab_labels_path = vocab_labels_path or VOCAB_LABELS_PATH
    cache_key = str(vocab_labels_path)

    if cache_key in _vocab_labels_cache:
        return _vocab_labels_cache[cache_key]

    if not vocab_labels_path.exists():
        _vocab_labels_cache[cache_key] = {}
        return _vocab_labels_cache[cache_key]

    with vocab_labels_path.open("r", encoding="utf-8") as file:
        _vocab_labels_cache[cache_key] = json.load(file)

    return _vocab_labels_cache[cache_key]


def resolve_gnd_vocab_uri(
    value: str,
    vocab_labels_path: Path | None = None,
) -> str | None:
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

    labels = load_vocab_labels(vocab_labels_path)

    label = labels.get(compact_id)
    code = compact_id.split("#")[-1]

    if label:
        return f"{label} ({code})"

    # Fallback: if no label is known, at least return the compact code.
    return code
