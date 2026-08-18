import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path to allow imports from config
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    DATA_DIR,
    GND_UPDATE_INITIAL_DELAY_SECONDS,
    GND_UPDATE_INTERVAL_HOURS,
    GND_UPDATE_LOCK_STALE_SECONDS,
)

LOG_DIR = DATA_DIR / "logs"
STATE_DIR = DATA_DIR / "state"
LOCK_FILE = STATE_DIR / "update.lock"


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def ensure_directories() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def log(message: str) -> None:
    ensure_directories()
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

    return age_seconds > GND_UPDATE_LOCK_STALE_SECONDS


def acquire_lock() -> bool:
    ensure_directories()

    if lock_exists():
        if lock_is_stale():
            log(
                "Update lock is stale (older than "
                f"{GND_UPDATE_LOCK_STALE_SECONDS}s). Removing and retrying."
            )
            LOCK_FILE.unlink()
        else:
            return False

    LOCK_FILE.write_text(timestamp(), encoding="utf-8")
    return True


def release_lock() -> None:
    if LOCK_FILE.exists():
        LOCK_FILE.unlink()


def run_update() -> None:
    command = [
        sys.executable,
        "scripts/run_daily_updates.py",
    ]

    log("RUN " + " ".join(command))
    subprocess.run(command, check=True)


def main() -> None:
    ensure_directories()

    interval_hours = GND_UPDATE_INTERVAL_HOURS
    initial_delay_seconds = GND_UPDATE_INITIAL_DELAY_SECONDS

    interval_seconds = int(interval_hours * 3600)

    log("Daily GND update scheduler started")
    log(f"Initial delay: {initial_delay_seconds} seconds")
    log(f"Interval: {interval_hours} hours")

    time.sleep(initial_delay_seconds)

    while True:
        if not acquire_lock():
            log("Update lock exists. Skipping this cycle.")
        else:
            try:
                log("Starting scheduled update")
                run_update()
                log("Scheduled update finished")
            except Exception as error:
                log(f"Scheduled update failed: {error}")
            finally:
                release_lock()

        log(f"Sleeping for {interval_seconds} seconds")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()
