"""
Shared download helpers used by both the GND LDS importer and the Getty
vocabularies importer.
"""

from pathlib import Path
from typing import Final

import requests

CHUNK_SIZE: Final[int] = 1024 * 1024


def get_filename_from_url(url: str) -> str:
    """
    Extracts the local filename from a URL.
    """

    return url.rstrip("/").split("/")[-1]


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


def download_file(
    url: str,
    output_path: Path,
    force: bool = False,
) -> None:
    """
    Downloads one file via streaming, resuming safely from a `.part` file on
    failure (any leftover `.part` file from a previous failed attempt is
    discarded and the download restarts from scratch - no byte-range resume).

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
