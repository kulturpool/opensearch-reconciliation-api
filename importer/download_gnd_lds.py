import argparse
from pathlib import Path
from typing import Final

import requests

GND_LDS_SOURCES: Final[dict[str, str]] = {
    "geografikum": "https://data.dnb.de/opendata/authorities-gnd-geografikum_lds.jsonld.gz",
    "koerperschaft": "https://data.dnb.de/opendata/authorities-gnd-koerperschaft_lds.jsonld.gz",
    "kongress": "https://data.dnb.de/opendata/authorities-gnd-kongress_lds.jsonld.gz",
    "person": "https://data.dnb.de/opendata/authorities-gnd-person_lds.jsonld.gz",
    "sachbegriff": "https://data.dnb.de/opendata/authorities-gnd-sachbegriff_lds.jsonld.gz",
    # Achtung: Für "werk" gibt es aktuell keinen stabilen JSON-LD-Link
    # authorities-gnd-werk_lds.jsonld.gz.
    # Daher nutzen wir vorerst den datierten JSON-LD-Abzug.
    "werk": "https://data.dnb.de/opendata/authorities-gnd-werk_lds_20260217.jsonld.gz",
    "entityfacts": "https://data.dnb.de/opendata/authorities-gnd_entityfacts.ndjson.gz",
}

DEFAULT_OUTPUT_DIR: Final[str] = "data/raw"
CHUNK_SIZE: Final[int] = 1024 * 1024


def get_filename_from_url(url: str) -> str:
    """
    Extracts the local filename from a URL.
    """

    return url.rstrip("/").split("/")[-1]


def download_file(
    url: str,
    output_path: Path,
    force: bool = False,
) -> None:
    """
    Downloads one file via streaming.

    Args:
        url: Source URL.
        output_path: Local target path.
        force: If True, overwrite an existing file.
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists() and not force:
        print(f"[SKIP] File already exists: {output_path}")
        print("       Use --force to download again.")
        return

    temporary_output_path = output_path.with_suffix(output_path.suffix + ".part")

    if temporary_output_path.exists():
        temporary_output_path.unlink()

    print(f"[DOWNLOAD] {url}")
    print(f"[TARGET]   {output_path}")

    with requests.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()

        total_bytes = response.headers.get("content-length")
        total_bytes_int = int(total_bytes) if total_bytes else None

        downloaded_bytes = 0

        with temporary_output_path.open("wb") as file:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if not chunk:
                    continue

                file.write(chunk)
                downloaded_bytes += len(chunk)

                print_progress(
                    downloaded_bytes=downloaded_bytes,
                    total_bytes=total_bytes_int,
                )

    temporary_output_path.rename(output_path)

    print()
    print(f"[DONE] {output_path}")


def print_progress(
    downloaded_bytes: int,
    total_bytes: int | None,
) -> None:
    """
    Prints a compact download progress indicator.
    """

    downloaded_mb = downloaded_bytes / 1024 / 1024

    if total_bytes:
        total_mb = total_bytes / 1024 / 1024
        percent = downloaded_bytes / total_bytes * 100

        print(
            f"\r        {downloaded_mb:,.1f} MB / {total_mb:,.1f} MB ({percent:5.1f}%)",
            end="",
            flush=True,
        )
    else:
        print(
            f"\r        {downloaded_mb:,.1f} MB",
            end="",
            flush=True,
        )


def download_source(
    source: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    force: bool = False,
) -> None:
    """
    Downloads one configured GND LDS source.

    Args:
        source: Source key, e.g. "person" or "sachbegriff".
        output_dir: Local output directory.
        force: If True, overwrite existing file.
    """

    if source not in GND_LDS_SOURCES:
        valid_sources = ", ".join(sorted(GND_LDS_SOURCES.keys()))
        raise ValueError(f"Unknown source: {source}. Valid sources: {valid_sources}")

    url = GND_LDS_SOURCES[source]
    filename = get_filename_from_url(url)
    output_path = Path(output_dir) / filename

    download_file(
        url=url,
        output_path=output_path,
        force=force,
    )


def download_all(
    output_dir: str = DEFAULT_OUTPUT_DIR,
    force: bool = False,
) -> None:
    """
    Downloads all configured GND LDS sources.
    """

    for source in GND_LDS_SOURCES:
        print()
        print(f"=== Source: {source} ===")
        download_source(
            source=source,
            output_dir=output_dir,
            force=force,
        )


def list_sources() -> None:
    """
    Prints all configured sources.
    """

    print("Available GND LDS sources:")
    print()

    for source, url in GND_LDS_SOURCES.items():
        filename = get_filename_from_url(url)

        print(f"- {source}")
        print(f"  URL:      {url}")
        print(f"  Filename: {filename}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Download DNB GND LDS JSON-LD dumps.")

    parser.add_argument(
        "--source",
        choices=[*GND_LDS_SOURCES.keys(), "all"],
        default="sachbegriff",
        help=(
            "Source to download. "
            "Use 'all' to download all GND LDS JSON-LD dumps. "
            "Default: sachbegriff"
        ),
    )

    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory. Default: {DEFAULT_OUTPUT_DIR}",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files.",
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="List available sources and exit.",
    )

    args = parser.parse_args()

    if args.list:
        list_sources()
        return

    if args.source == "all":
        download_all(
            output_dir=args.output_dir,
            force=args.force,
        )
    else:
        download_source(
            source=args.source,
            output_dir=args.output_dir,
            force=args.force,
        )


if __name__ == "__main__":
    main()
