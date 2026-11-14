"""Hidden acceptance test for case m02 (decaysim). Never shown to the executor.

The workspace path arrives in the WORKSPACE environment variable. Only the
documented entry point, run.sh, is used.
"""

import json
import math
import os
import subprocess
from pathlib import Path

import pytest

WORKSPACE = Path(os.environ["WORKSPACE"])


def run_pipeline(out, *args):
    done = subprocess.run(["bash", str(WORKSPACE / "run.sh"), str(out), *args], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    return json.loads((out / "summary.json").read_text())


def test_pipeline_halved_step_reaches_the_same_time(tmp_path):
    assert run_pipeline(tmp_path, "--dt", "0.05", "--steps", "20")["final_t"] == pytest.approx(1.0)


def test_pipeline_error_halves_with_the_step(tmp_path):
    coarse = run_pipeline(tmp_path / "coarse", "--dt", "0.1", "--steps", "10")["abs_error"]
    fine = run_pipeline(tmp_path / "fine", "--dt", "0.05", "--steps", "20")["abs_error"]
    assert 1.8 < coarse / fine < 2.2  # explicit Euler is first order


def test_pipeline_default_numbers_unchanged(tmp_path):
    result = run_pipeline(tmp_path)
    assert result["final_y"] == pytest.approx(0.9**10, rel=1e-12)
    assert result["exact_y"] == pytest.approx(math.exp(-1.0), rel=1e-12)
