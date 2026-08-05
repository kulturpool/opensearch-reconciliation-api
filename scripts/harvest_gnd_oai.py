import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


STATE_DIR = Path("data/state")
LOG_DIR = Path("data/logs")
UPDATE_STATE_FILE = STATE_DIR / "update_state.json"
CHANGED_IDS_FILE = STATE_DIR / "oai_changed_ids.jsonl"
DELETED_IDS_FILE = STATE_DIR / "oai_deleted_ids.jsonl"

OAI_BASE_URL = os.getenv(
    "GND_OAI_BASE_URL",
    "https://services.dnb.de/oai/repository",
)

OAI_SET = os.getenv("GND_OAI_SET") or None
OAI_METADATA_PREFIX = os.getenv("GND_OAI_METADATA_PREFIX", "RDFxml")
OAI_OVERLAP_MINUTES = int(os.getenv("GND_OAI_OVERLAP_MINUTES", "60"))

INDEX_NAME = os.getenv("GND_INDEX_NAME", "gnd")


OAI_NS = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
}


GND_ID_PATTERNS = [
    re.compile(r"https?://d-nb\.info/gnd/([^/#?\s\"<>]+)"),
    re.compile(r"https?://d-nb\.info/gnd/([^/#?\s\"<>]+)/about"),
    re.compile(r"oai:[^:\s\"<>]+:gnd:([^/\s\"<>]+)"),
    re.compile(r"oai:[^:\s\"<>]+:([^/\s\"<>]+)"),
]

GND_ID_VALID_PATTERN = re.compile(r"^[0-9Xx][0-9Xx-]*$")

CHANGED_RECORDS_FILE = STATE_DIR / "oai_changed_records.jsonl"

OAI_REQUEST_TIMEOUT_SECONDS = int(
    os.getenv("GND_OAI_REQUEST_TIMEOUT_SECONDS", "300")
)

OAI_REQUEST_MAX_RETRIES = int(
    os.getenv("GND_OAI_REQUEST_MAX_RETRIES", "6")
)

OAI_REQUEST_BACKOFF_SECONDS = float(
    os.getenv("GND_OAI_REQUEST_BACKOFF_SECONDS", "10")
)

OAI_PAGE_DELAY_SECONDS = float(
    os.getenv("GND_OAI_PAGE_DELAY_SECONDS", "2")
)


def timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def ensure_directories() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def log(message: str) -> None:
    ensure_directories()
    print(f"[{timestamp()}] {message}", flush=True)


def load_state() -> dict[str, Any]:
    if not UPDATE_STATE_FILE.exists():
        return {}

    return json.loads(UPDATE_STATE_FILE.read_text(encoding="utf-8"))


def write_state(state: dict[str, Any]) -> None:
    ensure_directories()

    UPDATE_STATE_FILE.write_text(
        json.dumps(
            state,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def parse_utc(value: str) -> datetime:
    value = value.replace("Z", "+00:00")
    return datetime.fromisoformat(value)


def format_oai_datetime(value: datetime) -> str:
    """
    Formats datetime for DNB OAI-PMH.

    DNB expects UTC timestamps with second precision:
    YYYY-MM-DDThh:mm:ssZ

    Microseconds are not accepted.
    """

    value = value.astimezone(timezone.utc)
    value = value.replace(microsecond=0)

    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def get_harvest_window(state: dict[str, Any]) -> tuple[str, str]:
    now = datetime.now(timezone.utc)

    last_harvest = state.get("last_oai_harvest")

    if last_harvest:
        from_dt = parse_utc(last_harvest) - timedelta(minutes=OAI_OVERLAP_MINUTES)
    else:
        # First incremental run: use last full import if available, otherwise yesterday.
        last_full_import = state.get("last_full_import")

        if last_full_import:
            from_dt = parse_utc(last_full_import) - timedelta(minutes=OAI_OVERLAP_MINUTES)
        else:
            from_dt = now - timedelta(days=1)

    until_dt = now

    return format_oai_datetime(from_dt), format_oai_datetime(until_dt)


def build_oai_url(params: dict[str, str]) -> str:
    return OAI_BASE_URL + "?" + urllib.parse.urlencode(params)


def fetch_url(url: str, timeout: int | None = None) -> bytes:
    """
    Fetches an OAI URL with retry/backoff.

    This is important because long OAI harvests use many resumptionToken
    requests and individual requests can occasionally time out.
    """

    request_timeout = timeout or OAI_REQUEST_TIMEOUT_SECONDS

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "local-gnd-reconciliation-api/0.1",
        },
    )

    last_error: Exception | None = None

    for attempt in range(1, OAI_REQUEST_MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=request_timeout) as response:
                return response.read()

        except urllib.error.HTTPError as error:
            last_error = error

            if error.code == 429:
                wait_seconds = max(
                    OAI_REQUEST_BACKOFF_SECONDS * attempt,
                    120,
                )
            else:
                wait_seconds = OAI_REQUEST_BACKOFF_SECONDS * attempt

            log(
                f"OAI HTTP error for {url}: {error}. "
                f"Retry {attempt}/{OAI_REQUEST_MAX_RETRIES} in {wait_seconds}s"
            )

            time.sleep(wait_seconds)

        except urllib.error.URLError as error:
            last_error = error
            wait_seconds = OAI_REQUEST_BACKOFF_SECONDS * attempt

            log(
                f"OAI URL error for {url}: {error}. "
                f"Retry {attempt}/{OAI_REQUEST_MAX_RETRIES} in {wait_seconds}s"
            )

            time.sleep(wait_seconds)

        except TimeoutError as error:
            last_error = error
            wait_seconds = OAI_REQUEST_BACKOFF_SECONDS * attempt

            log(
                f"OAI timeout for {url}: {error}. "
                f"Retry {attempt}/{OAI_REQUEST_MAX_RETRIES} in {wait_seconds}s"
            )

            time.sleep(wait_seconds)

    raise RuntimeError(
        f"OAI request failed after {OAI_REQUEST_MAX_RETRIES} retries: {url}. "
        f"Last error: {last_error}"
    )


def fetch_oai_list_records(
    from_time: str | None = None,
    until_time: str | None = None,
    resumption_token: str | None = None,
) -> ET.Element:
    if resumption_token:
        params = {
            "verb": "ListRecords",
            "resumptionToken": resumption_token,
        }
    else:
        params = {
            "verb": "ListRecords",
            "metadataPrefix": OAI_METADATA_PREFIX,
        }

        if OAI_SET:
            params["set"] = OAI_SET

        if from_time:
            params["from"] = from_time

        if until_time:
            params["until"] = until_time

    url = build_oai_url(params)

    log(f"OAI request: {url}")

    data = fetch_url(url)
    return ET.fromstring(data)


def get_oai_error(root: ET.Element) -> str | None:
    error = root.find("oai:error", OAI_NS)

    if error is None:
        return None

    code = error.attrib.get("code", "unknown")
    message = "".join(error.itertext()).strip()

    return f"{code}: {message}"


def extract_resumption_token(root: ET.Element) -> str | None:
    token = root.find(".//oai:resumptionToken", OAI_NS)

    if token is None:
        return None

    value = (token.text or "").strip()

    return value or None


def extract_gnd_id_from_text(text: str) -> str | None:
    if not text:
        return None

    for pattern in GND_ID_PATTERNS:
        match = pattern.search(text)

        if not match:
            continue

        value = match.group(1).strip().strip("/")

        if GND_ID_VALID_PATTERN.match(value):
            return value

    return None


def extract_gnd_id_from_oai_record(record: ET.Element) -> str | None:
    # 1. Try header identifier.
    header_identifier = record.findtext("oai:header/oai:identifier", default="", namespaces=OAI_NS)
    gnd_id = extract_gnd_id_from_text(header_identifier)

    if gnd_id:
        return gnd_id

    # 2. Try any rdf:about / about-like attribute or text in metadata.
    metadata = record.find("oai:metadata", OAI_NS)

    if metadata is None:
        return None

    metadata_text = ET.tostring(metadata, encoding="unicode")
    gnd_id = extract_gnd_id_from_text(metadata_text)

    if gnd_id:
        return gnd_id

    return None


def is_deleted_record(record: ET.Element) -> bool:
    header = record.find("oai:header", OAI_NS)

    if header is None:
        return False

    return header.attrib.get("status") == "deleted"


def append_jsonl(path: Path, item: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(item, ensure_ascii=False) + "\n")


def reset_output_files() -> None:
    ensure_directories()

    for path in [CHANGED_IDS_FILE, CHANGED_RECORDS_FILE, DELETED_IDS_FILE]:
        if path.exists():
            path.unlink()

def extract_metadata_xml(record: ET.Element) -> str | None:
    """
    Extracts the actual RDF/XML payload from an OAI record.

    OAI structure is:
      <record>
        <metadata>
          <rdf:RDF>...</rdf:RDF>
        </metadata>
      </record>

    rdflib must receive the inner <rdf:RDF> element, not the outer
    OAI <metadata> wrapper.
    """

    metadata = record.find("oai:metadata", OAI_NS)

    if metadata is None:
        return None

    children = list(metadata)

    if not children:
        return None

    # Usually the first and only child is <rdf:RDF>.
    rdf_root = children[0]

    return ET.tostring(rdf_root, encoding="unicode")


def soft_delete_ids(ids: list[str]) -> None:
    if not ids:
        return

    # Import here so this script can also be used just for harvesting/debugging.
    from opensearchpy import OpenSearch, helpers

    host = os.getenv("OPENSEARCH_HOST", "opensearch")
    port = int(os.getenv("OPENSEARCH_PORT", "9200"))

    client = OpenSearch(
        hosts=[{"host": host, "port": port}],
        http_compress=True,
        use_ssl=False,
        verify_certs=False,
        ssl_show_warn=False,
    )

    actions = []

    now = timestamp()

    for gnd_id in ids:
        actions.append(
            {
                "_op_type": "update",
                "_index": INDEX_NAME,
                "_id": gnd_id,
                "doc": {
                    "deleted": True,
                    "deprecated": True,
                    "lastUpdateAction": "delete",
                    "lastOaiUpdate": now,
                },
                "doc_as_upsert": True,
            }
        )

    success_count = 0
    error_count = 0

    for success, info in helpers.streaming_bulk(
        client=client,
        actions=actions,
        chunk_size=500,
        request_timeout=120,
        raise_on_error=False,
    ):
        if success:
            success_count += 1
        else:
            error_count += 1
            log(f"[ERROR] soft delete failed: {info}")

    log(f"Soft-deleted records: {success_count}, errors: {error_count}")


def run_upsert_changed_ids(ids_file: Path) -> None:
    if not ids_file.exists() or ids_file.stat().st_size == 0:
        log("No changed IDs to upsert.")
        return

    command = [
        sys.executable,
        "-m",
        "indexer.upsert_gnd_ids",
        "--ids-file",
        str(ids_file),
    ]

    log("RUN " + " ".join(command))
    subprocess.run(command, check=True)

def run_upsert_changed_records(records_file: Path) -> None:
    if not records_file.exists() or records_file.stat().st_size == 0:
        log("No changed OAI records to upsert.")
        return

    command = [
        sys.executable,
        "-m",
        "indexer.upsert_oai_records",
        "--records-file",
        str(records_file),
    ]

    log("RUN " + " ".join(command))
    subprocess.run(command, check=True)


def harvest_oai() -> dict[str, Any]:
    state = load_state()

    from_time, until_time = get_harvest_window(state)

    reset_output_files()

    log(f"OAI harvest window: {from_time} -> {until_time}")

    changed_ids: set[str] = set()
    deleted_ids: set[str] = set()

    resumption_token = None
    page_count = 0
    record_count = 0

    while True:
        root = fetch_oai_list_records(
            from_time=from_time,
            until_time=until_time,
            resumption_token=resumption_token,
        )

        error = get_oai_error(root)

        if error:
            # OAI noRecordsMatch is a valid empty update.
            if error.startswith("noRecordsMatch"):
                log("OAI returned noRecordsMatch.")
                break

            raise RuntimeError(f"OAI error: {error}")

        records = root.findall(".//oai:record", OAI_NS)
        page_count += 1

        log(f"OAI page {page_count}: {len(records)} records")

        for record in records:
            record_count += 1

            gnd_id = extract_gnd_id_from_oai_record(record)

            if not gnd_id:
                log("Skipping OAI record without extractable GND ID")
                continue

            if is_deleted_record(record):
                deleted_ids.add(gnd_id)
                append_jsonl(
                    DELETED_IDS_FILE,
                    {
                        "id": gnd_id,
                        "action": "delete",
                    },
                )
            else:
                metadata_xml = extract_metadata_xml(record)

                if not metadata_xml:
                    log(f"Skipping changed record without metadata XML: {gnd_id}")
                    continue

                changed_ids.add(gnd_id)

                append_jsonl(
                    CHANGED_RECORDS_FILE,
                    {
                        "id": gnd_id,
                        "action": "upsert",
                        "metadata_xml": metadata_xml,
                    },
                )

        resumption_token = extract_resumption_token(root)

        if not resumption_token:
            break

        # Be polite to the provider.
        if OAI_PAGE_DELAY_SECONDS > 0:
            time.sleep(OAI_PAGE_DELAY_SECONDS)

    deleted_list = sorted(deleted_ids)
    changed_list = sorted(changed_ids - deleted_ids)

    log(f"OAI records seen: {record_count}")
    log(f"Changed IDs:      {len(changed_list)}")
    log(f"Deleted IDs:      {len(deleted_list)}")

    # Apply updates.
    if changed_list:
        run_upsert_changed_records(CHANGED_RECORDS_FILE)

    if deleted_list:
        soft_delete_ids(deleted_list)

    state["last_oai_harvest"] = until_time
    state["last_successful_update"] = timestamp()
    state["last_error"] = None
    state["updates"] = {
        "oai_records_seen": record_count,
        "changed": len(changed_list),
        "deleted": len(deleted_list),
        "pages": page_count,
    }

    write_state(state)

    return state["updates"]


def main() -> None:
    ensure_directories()

    try:
        stats = harvest_oai()
        log(f"OAI harvest completed: {stats}")

    except Exception as error:
        state = load_state()

        state["last_error"] = str(error)
        state["last_failed_update"] = timestamp()

        # Preserve last_oai_harvest intentionally.
        # Do not advance it after a failed update.
        write_state(state)

        log(f"OAI harvest failed: {error}")

        raise


if __name__ == "__main__":
    main()