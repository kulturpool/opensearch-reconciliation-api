import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


LOG_DIR = Path("data/logs")
STATE_DIR = Path("data/state")
LOCK_FILE = STATE_DIR / "update.lock"


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_directories() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def log(message: str) -> None:
    ensure_directories()
    print(f"[{timestamp()}] {message}", flush=True)


def lock_exists() -> bool:
    return LOCK_FILE.exists()


def acquire_lock() -> bool:
    ensure_directories()

    if lock_exists():
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

    interval_hours = float(os.getenv("GND_UPDATE_INTERVAL_HOURS", "24"))
    initial_delay_seconds = int(os.getenv("GND_UPDATE_INITIAL_DELAY_SECONDS", "300"))

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