"""
Periodically triggers a full Getty rebuild via scripts/update_getty.py.

Mirrors scripts/update_scheduler.py's structure (own simple file-based lock,
initial delay, sleep loop), but targets Getty's config vars and a separate
lock file so it never interferes with GND's independent update scheduler.
"""

import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path to allow imports from config
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    DATA_DIR,
    GETTY_UPDATE_INITIAL_DELAY_SECONDS,
    GETTY_UPDATE_INTERVAL_HOURS,
    GETTY_UPDATE_LOCK_STALE_SECONDS,
)

STATE_DIR = DATA_DIR / "state"
LOCK_FILE = STATE_DIR / "getty_update.lock"


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def ensure_directories() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def log(message: str) -> None:
    print(f"[{timestamp()}] {message}", flush=True)


def lock_exists() -> bool:
    return LOCK_FILE.exists()


def lock_is_stale() -> bool:
    if not LOCK_FILE.exists():
        return False

    try:
        raw_timestamp = LOCK_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return False

    created_at = parse_timestamp(raw_timestamp)
    if created_at is None:
        return True

    age_seconds = (datetime.now(timezone.utc) - created_at).total_seconds()
    return age_seconds > GETTY_UPDATE_LOCK_STALE_SECONDS


def acquire_lock() -> bool:
    ensure_directories()

    if lock_exists():
        if lock_is_stale():
            log("Removing stale Getty update lock.")
            LOCK_FILE.unlink()
        else:
            return False

    LOCK_FILE.write_text(timestamp(), encoding="utf-8")
    return True


def release_lock() -> None:
    if LOCK_FILE.exists():
        LOCK_FILE.unlink()


def run_update() -> None:
    log("Starting scheduled Getty full rebuild")
    subprocess.run(
        [sys.executable, "scripts/update_getty.py"],
        check=True,
    )
    log("Scheduled Getty full rebuild finished")


def main() -> None:
    ensure_directories()

    initial_delay_seconds = GETTY_UPDATE_INITIAL_DELAY_SECONDS
    interval_seconds = GETTY_UPDATE_INTERVAL_HOURS * 60 * 60

    log(
        f"Getty update scheduler starting. Initial delay: "
        f"{initial_delay_seconds}s, interval: {GETTY_UPDATE_INTERVAL_HOURS}h"
    )
    time.sleep(initial_delay_seconds)

    while True:
        if not acquire_lock():
            log("Getty update lock held by another process. Skipping this cycle.")
        else:
            try:
                run_update()
            except Exception as error:  # noqa: BLE001 - log and keep scheduling
                log(f"Getty scheduled update failed: {error}")
            finally:
                release_lock()

        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()
