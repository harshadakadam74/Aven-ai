"""Run every Python test suite:  python scripts/run_tests.py"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUITES = [ROOT / "backend", ROOT / "apps" / "windows"]

failed = False
for suite in SUITES:
    print(f"\n=== {suite.relative_to(ROOT)} ===", flush=True)
    code = subprocess.call(
        [sys.executable, "-I", "-m", "unittest", "discover", "-s", "tests", "-t", "."],
        cwd=suite,
    )
    failed = failed or code != 0
sys.exit(1 if failed else 0)
