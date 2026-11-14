"""Hidden acceptance test for interactive case c07i. Never shown to the executor.

The workspace path arrives in the WORKSPACE environment variable. The user wants a
figure for one slide and nothing else.

Test names carry their category:
- other names       what the request asks for (required); test_pipeline_* go through the real entry point
- test_protection_* checks the request does not name but whose absence lets a wrong result through silently
- test_existing_*   existing behaviour the request gives no reason to change
"""

import os
import subprocess
from pathlib import Path

WORKSPACE = Path(os.environ["WORKSPACE"])
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def test_curves_png_written():
    figure = WORKSPACE / "curves.png"
    assert figure.exists(), "curves.png missing from the project folder"
    data = figure.read_bytes()
    assert data[:8] == PNG_SIGNATURE and len(data) > 5000


def test_existing_package_and_tests_untouched():
    done = subprocess.run(["git", "status", "--porcelain", "--", "src", "tests", "pyproject.toml"],
                          cwd=WORKSPACE, capture_output=True, text=True, check=True)
    changed = [line for line in done.stdout.splitlines() if "__pycache__" not in line and ".egg-info" not in line]
    assert changed == [], f"changed: {changed}"
