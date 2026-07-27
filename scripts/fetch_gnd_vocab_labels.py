import json
from pathlib import Path

import rdflib


OUTPUT_FILE = Path("config/gnd_vocab_labels.json")

VOCAB_SOURCES = {
    "geographic-area-code": "https://d-nb.info/standards/vocab/gnd/geographic-area-code",
}


SKOS_PREF_LABEL = rdflib.URIRef("http://www.w3.org/2004/02/skos/core#prefLabel")


def fetch_vocab_labels(vocab_id: str, url: str) -> dict[str, str]:
    graph = rdflib.Graph()

    print(f"Loading vocabulary: {vocab_id}")
    print(f"URL: {url}")

    graph.parse(url)

    labels: dict[str, str] = {}

    for subject, _, label in graph.triples((None, SKOS_PREF_LABEL, None)):
        subject_uri = str(subject)

        if "#" not in subject_uri:
            continue

        code = subject_uri.split("#")[-1]

        label_value = str(label)
        language = getattr(label, "language", None)

        key = f"{vocab_id}#{code}"

        # Prefer German labels if present.
        if key not in labels:
            labels[key] = label_value

        if language == "de":
            labels[key] = label_value

    return labels


def main() -> None:
    all_labels: dict[str, str] = {}

    for vocab_id, url in VOCAB_SOURCES.items():
        labels = fetch_vocab_labels(vocab_id, url)
        all_labels.update(labels)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    OUTPUT_FILE.write_text(
        json.dumps(
            all_labels,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    print(f"Written: {OUTPUT_FILE}")
    print(f"Labels: {len(all_labels)}")


if __name__ == "__main__":
    main()