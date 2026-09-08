"""
Downloads Getty Vocabulary Program explicit exports (N-Triples zips).

v1 ships AAT only; ULAN and TGN are configured so enabling them later is a
one-line config change plus one reindex (per FINAL PLAN section 1).
"""

import argparse
import sys
import zipfile
from pathlib import Path
from typing import Final

# Add parent directory to path to allow imports from config
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import GETTY_DOWNLOAD_URL_TEMPLATE, GETTY_RAW_DIR
from importer.download_utils import download_file

# Files actually needed for reconciliation (see FINAL PLAN / repo memory:
# GETTY AAT EXPLICIT EXPORT — VERIFIED FILE SCHEMA). Skipping
# RevisionHistory/RevisionHistorySource/SourceRels/ContribRels/Sources/Contribs/
# Lang_sameAs/OrderedCollections/SemanticLinks/TermsTest/WikidataAlignment saves
# ~1.8GB of unzipped disk space per vocabulary.
GETTY_SOURCES: Final[dict[str, dict[str, str]]] = {
    "aat": {
        "file_prefix": "AATOut",
        "needed_files": (
            "AATOut_1Subjects.nt",
            "AATOut_2Terms.nt",
            "AATOut_ScopeNotes.nt",
            "AATOut_HierarchicalRels.nt",
            "AATOut_AssociativeRels.nt",
            "AATOut_Notations.nt",
            "AATOut_LCSHAlignment.nt",
            "AATOut_ObsoleteSubjects.nt",
        ),
    },
    # ULAN/TGN: design-prepared stubs, not implemented in v1 (out of scope per
    # FINAL PLAN section 8). Filling these in + adding the matching
    # `importer.getty_vocab_specs` entry is the only work needed to enable them.
    "ulan": {
        "file_prefix": "ULANOut",
        "needed_files": (
            "ULANOut_1Subjects.nt",
            "ULANOut_2Terms.nt",
            "ULANOut_ScopeNotes.nt",
            "ULANOut_HierarchicalRels.nt",
            "ULANOut_AssociativeRels.nt",
            "ULANOut_LOCAlignment.nt",
            "ULANOut_ObsoleteSubjects.nt",
            "ULANOut_Nationality.nt",
            "ULANOut_AgentTypes.nt",
            "ULANOut_Biographies.nt",
            "ULANOut_AgentMap.nt",
            "ULANOut_Event.nt",
        ),
    },
    "tgn": {
        "file_prefix": "TGNOut",
        "needed_files": (
            "TGNOut_1Subjects.nt",
            "TGNOut_2Terms.nt",
            "TGNOut_ScopeNotes.nt",
            "TGNOut_HierarchicalRels.nt",
            "TGNOut_AssociativeRels.nt",
            "TGNOut_ObsoleteSubjects.nt",
            "TGNOut_Coordinates.nt",
            "TGNOut_PlaceTypes.nt",
        ),
    },
}


def get_zip_path(vocab: str, raw_dir: Path = GETTY_RAW_DIR) -> Path:
    return raw_dir / vocab / "explicit.zip"


def download_vocab_zip(
    vocab: str,
    raw_dir: Path = GETTY_RAW_DIR,
    force: bool = False,
    url_template: str = GETTY_DOWNLOAD_URL_TEMPLATE,
) -> Path:
    """
    Downloads one Getty vocabulary's explicit.zip export.
    """

    if vocab not in GETTY_SOURCES:
        valid = ", ".join(sorted(GETTY_SOURCES.keys()))
        raise ValueError(f"Unknown Getty vocabulary: {vocab}. Valid: {valid}")

    url = url_template.format(vocab=vocab)
    zip_path = get_zip_path(vocab, raw_dir)

    download_file(url=url, output_path=zip_path, force=force)

    return zip_path


def extract_needed_files(
    vocab: str,
    zip_path: Path,
    force: bool = False,
) -> list[Path]:
    """
    Extracts only the `.nt` files needed for reconciliation from the
    downloaded explicit.zip into the same directory as the zip.
    """

    if vocab not in GETTY_SOURCES:
        valid = ", ".join(sorted(GETTY_SOURCES.keys()))
        raise ValueError(f"Unknown Getty vocabulary: {vocab}. Valid: {valid}")

    needed_files = GETTY_SOURCES[vocab]["needed_files"]

    if not needed_files:
        raise ValueError(
            f"No needed_files configured for vocabulary '{vocab}' yet "
            "(ULAN/TGN are design-prepared stubs, not implemented in v1)."
        )

    output_dir = zip_path.parent
    extracted_paths: list[Path] = []

    with zipfile.ZipFile(zip_path) as archive:
        available = set(archive.namelist())

        for filename in needed_files:
            output_path = output_dir / filename

            if output_path.exists() and not force:
                print(f"[SKIP] Already extracted: {output_path}")
                extracted_paths.append(output_path)
                continue

            if filename not in available:
                raise FileNotFoundError(
                    f"'{filename}' not found in {zip_path}. "
                    f"Available files: {sorted(available)}"
                )

            print(f"[EXTRACT] {filename} -> {output_path}")
            archive.extract(filename, path=output_dir)
            extracted_paths.append(output_path)

    return extracted_paths


def download_and_extract(
    vocab: str,
    raw_dir: Path = GETTY_RAW_DIR,
    force: bool = False,
    url_template: str = GETTY_DOWNLOAD_URL_TEMPLATE,
) -> list[Path]:
    """
    Downloads (if needed) and extracts the reconciliation-relevant `.nt`
    files for one Getty vocabulary.
    """

    zip_path = download_vocab_zip(
        vocab=vocab,
        raw_dir=raw_dir,
        force=force,
        url_template=url_template,
    )

    return extract_needed_files(vocab=vocab, zip_path=zip_path, force=force)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download Getty Vocabulary Program explicit exports."
    )

    parser.add_argument(
        "--source",
        choices=sorted(GETTY_SOURCES.keys()),
        default="aat",
        help="Getty vocabulary to download. Default: aat",
    )

    parser.add_argument(
        "--raw-dir",
        default=str(GETTY_RAW_DIR),
        help=f"Output directory. Default: {GETTY_RAW_DIR}",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download the zip and re-extract files even if already present.",
    )

    parser.add_argument(
        "--zip-only",
        action="store_true",
        help="Only download the zip, do not extract.",
    )

    args = parser.parse_args()

    raw_dir = Path(args.raw_dir)

    if args.zip_only:
        download_vocab_zip(vocab=args.source, raw_dir=raw_dir, force=args.force)
        return

    extracted = download_and_extract(vocab=args.source, raw_dir=raw_dir, force=args.force)

    print()
    print(f"[DONE] Extracted {len(extracted)} file(s) for '{args.source}'.")


if __name__ == "__main__":
    main()
