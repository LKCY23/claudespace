"""Hidden acceptance test for case m01 (decaysim). Never shown to the executor.

The workspace path arrives in the WORKSPACE environment variable. Only the
documented entry point, run.sh, is used.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

WORKSPACE = Path(os.environ["WORKSPACE"])


def run_pipeline(out, *args):
    return subprocess.run(["bash", str(WORKSPACE / "run.sh"), str(out), *args], capture_output=True, text=True, timeout=120)


def summary(out):
    return json.loads((out / "summary.json").read_text())


def test_pipeline_default_is_euler_with_unchanged_numbers(tmp_path):
    done = run_pipeline(tmp_path)
    assert done.returncode == 0, done.stderr
    assert summary(tmp_path)["final_y"] == pytest.approx(0.9**10, rel=1e-12)
    assert summary(tmp_path)["method"] == "euler"


def test_pipeline_midpoint_matches_hand_value(tmp_path):
    # For dy/dt = -k y one midpoint step multiplies y by 1 - k dt + (k dt)^2 / 2.
    done = run_pipeline(tmp_path, "--method", "midpoint")
    assert done.returncode == 0, done.stderr
    assert summary(tmp_path)["final_y"] == pytest.approx((1 - 0.1 + 0.005) ** 10, rel=1e-12)
    assert summary(tmp_path)["method"] == "midpoint"


def test_pipeline_midpoint_is_more_accurate_than_euler(tmp_path):
    run_pipeline(tmp_path / "euler")
    run_pipeline(tmp_path / "midpoint", "--method", "midpoint")
    assert summary(tmp_path / "midpoint")["abs_error"] < summary(tmp_path / "euler")["abs_error"] / 5


def test_pipeline_rejects_unknown_method(tmp_path):
    assert run_pipeline(tmp_path, "--method", "rk4").returncode != 0
