import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Add parent directory to path to allow imports from config
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DATA_DIR, GND_INDEX_LOCK_STALE_SECONDS

STATE_DIR = DATA_DIR / "state"

# GND keeps its original, unprefixed filenames for backward compatibility
# (existing deployments already have data/state/index_state.json etc. on
# disk). Any other vocab (e.g. "getty") gets a "<vocab>_" prefixed filename.
INDEX_STATE_FILE = STATE_DIR / "index_state.json"
INDEX_COMPLETE_MARKER = STATE_DIR / "index_complete.marker"
INDEX_LOCK_FILE = STATE_DIR / "index_build.lock"


def _state_paths(vocab: str) -> tuple[Path, Path, Path]:
    """
    Returns (state_file, complete_marker, lock_file) for a given vocab key.
    """
    if vocab == "gnd":
        return (INDEX_STATE_FILE, INDEX_COMPLETE_MARKER, INDEX_LOCK_FILE)

    return (
        STATE_DIR / f"{vocab}_index_state.json",
        STATE_DIR / f"{vocab}_index_complete.marker",
        STATE_DIR / f"{vocab}_index_build.lock",
    )


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


def read_index_state(vocab: str = "gnd") -> dict[str, Any]:
    state_file, _, _ = _state_paths(vocab)

    if not state_file.exists():
        return {}

    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    except OSError:
        return {}


def mark_index_build_started(build_index: str, vocab: str = "gnd") -> None:
    state_file, complete_marker, _ = _state_paths(vocab)
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    if complete_marker.exists():
        complete_marker.unlink()

    write_json_atomic(
        state_file,
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
    vocab: str = "gnd",
) -> None:
    state_file, complete_marker, _ = _state_paths(vocab)
    previous_state = read_index_state(vocab=vocab)

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

    write_json_atomic(state_file, state)
    complete_marker.write_text(timestamp(), encoding="utf-8")


def mark_index_build_failed(error: str, vocab: str = "gnd") -> None:
    state_file, _, _ = _state_paths(vocab)
    state = read_index_state(vocab=vocab)
    state.update(
        {
            "status": "failed",
            "failed_at": timestamp(),
            "last_error": error,
        }
    )
    write_json_atomic(state_file, state)


def index_state_complete(require_entityfacts: bool = True, vocab: str = "gnd") -> bool:
    _, complete_marker, _ = _state_paths(vocab)
    state = read_index_state(vocab=vocab)

    if state.get("status") != "complete":
        return False

    if not complete_marker.exists():
        return False

    return not require_entityfacts or state.get("entityfacts_indexed", False)


def lock_is_stale(
    vocab: str = "gnd",
    stale_seconds: int = GND_INDEX_LOCK_STALE_SECONDS,
) -> bool:
    _, _, lock_file = _state_paths(vocab)

    if not lock_file.exists():
        return False

    try:
        raw_timestamp = lock_file.read_text(encoding="utf-8").strip()
    except OSError:
        return False

    created_at = parse_timestamp(raw_timestamp)
    if created_at is None:
        return True

    age_seconds = (datetime.now(timezone.utc) - created_at).total_seconds()
    return age_seconds > stale_seconds


def acquire_index_lock(
    vocab: str = "gnd",
    stale_seconds: int = GND_INDEX_LOCK_STALE_SECONDS,
) -> None:
    _, _, lock_file = _state_paths(vocab)
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    if lock_file.exists():
        if lock_is_stale(vocab=vocab, stale_seconds=stale_seconds):
            lock_file.unlink()
        else:
            raise RuntimeError(
                f"Index build lock exists: {lock_file}. "
                "Another index build may be running or a previous build was interrupted. "
                "If you are sure no build is running, delete this file manually."
            )

    lock_file.write_text(timestamp(), encoding="utf-8")


def release_index_lock(vocab: str = "gnd") -> None:
    _, _, lock_file = _state_paths(vocab)

    if lock_file.exists():
        lock_file.unlink()
