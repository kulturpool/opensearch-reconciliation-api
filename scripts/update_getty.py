"""
Runs a scheduled Getty full rebuild.

Unlike GND's OAI-PMH incremental harvest (scripts/run_daily_updates.py),
Getty has no incremental update source: the only way to pick up changes in
the Getty Vocabulary Program's AAT export is a full re-download + reindex.
This script simply forces scripts.bootstrap_getty's --init full build.
"""

import subprocess
import sys
from pathlib import Path

# Add parent directory to path to allow imports from config
sys.path.insert(0, str(Path(__file__).parent.parent))


def main() -> None:
    subprocess.run(
        [sys.executable, "-m", "scripts.bootstrap_getty", "--init"],
        check=True,
    )


if __name__ == "__main__":
    main()
