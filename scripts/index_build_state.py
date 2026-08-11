import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Add parent directory to path to allow imports from config
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DATA_DIR, GND_INDEX_LOCK_STALE_SECONDS

STATE_DIR = DATA_DIR / "state"
INDEX_STATE_FILE = STATE_DIR / "index_state.json"
INDEX_COMPLETE_MARKER = STATE_DIR / "index_complete.marker"
INDEX_LOCK_FILE = STATE_DIR / "index_build.lock"


def timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    temp_path.replace(path)


def read_index_state() -> dict[str, Any]:
    if not INDEX_STATE_FILE.exists():
        return {}

    try:
        return json.loads(INDEX_STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    except OSError:
        return {}


def mark_index_build_started(build_index: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    if INDEX_COMPLETE_MARKER.exists():
        INDEX_COMPLETE_MARKER.unlink()

    write_json_atomic(
        INDEX_STATE_FILE,
        {
            "status": "running",
            "started_at": timestamp(),
            "completed_at": None,
            "failed_at": None,
            "last_error": None,
            "build_index": build_index,
            "active_index": None,
            "document_count": None,
            "family_count": None,
            "entityfacts_count": None,
            "entityfacts_indexed": False,
        },
    )


def mark_index_build_complete(
    active_index: str,
    document_count: int,
    family_count: int | None = None,
    entityfacts_count: int | None = None,
    entityfacts_indexed: bool = True,
) -> None:
    previous_state = read_index_state()

    state = {
        "status": "complete",
        "started_at": previous_state.get("started_at"),
        "completed_at": timestamp(),
        "failed_at": None,
        "last_error": None,
        "active_index": active_index,
        "build_index": previous_state.get("build_index"),
        "document_count": document_count,
        "family_count": family_count,
        "entityfacts_count": entityfacts_count,
        "entityfacts_indexed": entityfacts_indexed,
    }

    write_json_atomic(INDEX_STATE_FILE, state)
    INDEX_COMPLETE_MARKER.write_text(timestamp(), encoding="utf-8")


def mark_index_build_failed(error: str) -> None:
    state = read_index_state()
    state.update(
        {
            "status": "failed",
            "failed_at": timestamp(),
            "last_error": error,
        }
    )
    write_json_atomic(INDEX_STATE_FILE, state)


def index_state_complete(require_entityfacts: bool = True) -> bool:
    state = read_index_state()

    if state.get("status") != "complete":
        return False

    if not INDEX_COMPLETE_MARKER.exists():
        return False

    return not require_entityfacts or state.get("entityfacts_indexed", False)


def lock_is_stale() -> bool:
    if not INDEX_LOCK_FILE.exists():
        return False

    try:
        raw_timestamp = INDEX_LOCK_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return False

    created_at = parse_timestamp(raw_timestamp)
    if created_at is None:
        return True

    age_seconds = (datetime.now(timezone.utc) - created_at).total_seconds()
    return age_seconds > GND_INDEX_LOCK_STALE_SECONDS


def acquire_index_lock() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    if INDEX_LOCK_FILE.exists():
        if lock_is_stale():
            INDEX_LOCK_FILE.unlink()
        else:
            raise RuntimeError(
                f"Index build lock exists: {INDEX_LOCK_FILE}. "
                "Another index build may be running or a previous build was interrupted. "
                "If you are sure no build is running, delete this file manually."
            )

    INDEX_LOCK_FILE.write_text(timestamp(), encoding="utf-8")


def release_index_lock() -> None:
    if INDEX_LOCK_FILE.exists():
        INDEX_LOCK_FILE.unlink()
