import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATE_DIR = Path("data/state")
UPDATE_STATE_FILE = STATE_DIR / "update_state.json"


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state() -> dict[str, Any]:
    if not UPDATE_STATE_FILE.exists():
        return {}

    return json.loads(
        UPDATE_STATE_FILE.read_text(encoding="utf-8")
    )


def write_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    UPDATE_STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def run_command(command: list[str]) -> None:
    print(f"[{timestamp()}] RUN {' '.join(command)}", flush=True)
    subprocess.run(command, check=True)


def main() -> None:
    state = load_state()

    state["last_update_check"] = timestamp()
    write_state(state)

    run_command(
        [
            sys.executable,
            "scripts/harvest_gnd_oai.py",
        ]
    )

    state = load_state()
    state["last_successful_update"] = timestamp()
    state["last_error"] = None
    write_state(state)


if __name__ == "__main__":
    main()