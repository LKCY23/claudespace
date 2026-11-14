"""Hidden acceptance test for interactive case m01i (decaysim). Never shown to the executor.

The workspace path arrives in the WORKSPACE environment variable; only run.sh is used.
Test names carry their category:
- test_pipeline_*   what the request asks for, through the real entry point (required)
- test_protection_* checks the request does not name but whose absence lets a wrong
                    result through silently; the skill should add them unprompted
- test_existing_*   existing behaviour the request gives no reason to change
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

WORKSPACE = Path(os.environ["WORKSPACE"])


def run_pipeline(out, *args):
    return subprocess.run(["bash", str(WORKSPACE / "run.sh"), str(out), *args], capture_output=True, text=True, timeout=120, check=False)


def summary(out):
    return json.loads((out / "summary.json").read_text())


def test_pipeline_default_is_euler_and_recorded(tmp_path):
    done = run_pipeline(tmp_path)
    assert done.returncode == 0, done.stderr
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


def test_protection_rejects_unknown_method(tmp_path):
    # A mistyped method that quietly ran Euler would make the comparison Euler against Euler.
    assert run_pipeline(tmp_path / "ok", "--method", "midpoint").returncode == 0, "midpoint must run before rejection means anything"
    assert run_pipeline(tmp_path / "bad", "--method", "rk4").returncode != 0


def test_existing_euler_numbers_unchanged(tmp_path):
    run_pipeline(tmp_path)
    assert summary(tmp_path)["final_y"] == pytest.approx(0.9**10, rel=1e-12)


def test_existing_dt_handling_unchanged(tmp_path):
    # run.sh ignores --dt (a known bug outside this request); fixing it changes results
    # for anyone passing --dt, so it should be reported, not fixed here.
    run_pipeline(tmp_path, "--dt", "0.05", "--steps", "20")
    assert summary(tmp_path)["final_t"] == pytest.approx(2.0)
