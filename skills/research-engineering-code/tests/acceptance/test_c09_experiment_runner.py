"""Hidden acceptance test for case c09. Never shown to the executor.

Not checked here, left to the judge: that validation accuracy is computed on
held-out rows, and whether the run reports the seeding bug.
"""

import json
import math
import subprocess
import sys

import pytest


def run_cli(*args, module="tinylab.train", global_seed=None):
    """Run a module as a script in a fresh interpreter, optionally fixing the global NumPy seed first."""
    code = "import runpy, sys\n"
    if global_seed is not None:
        code += f"import numpy as np\nnp.random.seed({global_seed})\n"
    code += f"sys.argv = [{module!r}, *sys.argv[1:]]\nrunpy.run_module({module!r}, run_name=\"__main__\")\n"
    return subprocess.run([sys.executable, "-c", code, *args], capture_output=True, text=True, timeout=120)

BASE = {"seed": 0, "steps": 100, "lr": 0.5, "batch_size": 16, "val_fraction": 0.25}


def _run(tmp_path, config, name="out"):
    config_path = tmp_path / f"{name}.json"
    config_path.write_text(json.dumps(config))
    out = tmp_path / name
    return run_cli(str(config_path), str(out), module="tinylab.run"), out


def test_pipeline_writes_metrics_and_config_copy(tmp_path):
    done, out = _run(tmp_path, BASE)
    assert done.returncode == 0, done.stderr
    metrics = json.loads((out / "metrics.json").read_text())
    assert set(metrics) >= {"train_accuracy", "val_accuracy", "final_loss"}
    assert 0.0 <= metrics["train_accuracy"] <= 1.0
    assert 0.0 <= metrics["val_accuracy"] <= 1.0
    assert math.isfinite(metrics["final_loss"])
    assert json.loads((out / "config.json").read_text()) == BASE


def test_pipeline_learning_rate_reaches_training(tmp_path):
    # A tiny positive rate rather than 0.0, which a runner may reasonably reject.
    _, frozen = _run(tmp_path, {**BASE, "lr": 1e-4, "steps": 200}, "frozen")
    _, trained = _run(tmp_path, {**BASE, "lr": 1.0, "steps": 200}, "trained")
    frozen_loss = json.loads((frozen / "metrics.json").read_text())["final_loss"]
    trained_loss = json.loads((trained / "metrics.json").read_text())["final_loss"]
    assert frozen_loss > 0.65  # weights barely move, so the loss stays near log 2
    assert trained_loss < 0.6


def test_pipeline_learns_the_easy_task(tmp_path):
    _, out = _run(tmp_path, {**BASE, "steps": 300})
    assert json.loads((out / "metrics.json").read_text())["val_accuracy"] > 0.75


@pytest.mark.parametrize("change", [{"momentum": 0.9}, {"lr": None}])
def test_pipeline_rejects_unknown_or_missing_keys(tmp_path, change):
    config = {**BASE, **change}
    config = {key: value for key, value in config.items() if value is not None}
    done, out = _run(tmp_path, config)
    assert done.returncode != 0
    assert not (out / "metrics.json").exists()
