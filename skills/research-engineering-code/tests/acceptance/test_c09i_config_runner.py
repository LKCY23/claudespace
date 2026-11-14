"""Hidden acceptance test for interactive case c09i. Never shown to the executor.

Test names carry their category:
- test_pipeline_*   what the request asks for, through the real entry point (required)
- test_protection_* checks the request does not name but whose absence lets a wrong
                    result through silently; the skill should add them unprompted
- test_existing_*   existing behaviour the request gives no reason to change
"""

import json
import math
import subprocess
import sys

import numpy as np
import pytest

from tinylab.train import train


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
def test_protection_rejects_unknown_or_missing_keys(tmp_path, change):
    config = {**BASE, **change}
    config = {key: value for key, value in config.items() if value is not None}
    assert _run(tmp_path, BASE, "valid")[0].returncode == 0, "a valid config must run before rejection means anything"
    done, out = _run(tmp_path, config)
    assert done.returncode != 0
    assert not (out / "metrics.json").exists()


def test_protection_same_config_gives_identical_metrics(tmp_path):
    _, first = _run(tmp_path, BASE, "first")
    _, second = _run(tmp_path, BASE, "second")
    assert (first / "metrics.json").read_text() == (second / "metrics.json").read_text()


# Recorded from the untouched fixture: tinylab.train must keep producing these (brief B6).
REFERENCE_HISTORY = [
    0.693488012681, 0.647365465805, 0.632936631761, 0.576236155835, 0.569153080402,
    0.493739726954, 0.506873254115, 0.482944159267, 0.515296760835, 0.441166729373,
    0.470507469059, 0.425139545034, 0.325796750528, 0.556718102838, 0.391916759218,
    0.387959762227, 0.426239225421, 0.400623127069, 0.453304421535, 0.371040394219,
]


def test_existing_train_numbers_unchanged():
    np.random.seed(123)  # the fixture shuffles with the global state
    np.testing.assert_allclose(train(seed=0, steps=20)["history"], REFERENCE_HISTORY, atol=1e-9)


def test_existing_train_output_unchanged():
    done = run_cli("--seed", "0", "--steps", "60", global_seed=123)
    assert done.returncode == 0, done.stderr
    assert done.stdout == "step 0 loss 0.6935\nstep 50 loss 0.3762\nfinal accuracy 0.890\n"


@pytest.mark.parametrize("fraction", [1.5, 0.0])
def test_protection_rejects_split_with_no_training_or_validation_data(tmp_path, fraction):
    # A fraction of 1.5 or 0 leaves one split empty; accuracy on it would be meaningless.
    assert _run(tmp_path, BASE, "valid")[0].returncode == 0, "a valid config must run before rejection means anything"
    done, out = _run(tmp_path, {**BASE, "val_fraction": fraction})
    assert done.returncode != 0
    assert not (out / "metrics.json").exists()
