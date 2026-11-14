"""Hidden acceptance test for case c01. Never shown to the executor."""

import math
import subprocess
import sys

import numpy as np
import pytest

from tinylab.losses import binary_cross_entropy
from tinylab.train import train


def run_cli(*args, module="tinylab.train", global_seed=None):
    """Run a module as a script in a fresh interpreter, optionally fixing the global NumPy seed first."""
    code = "import runpy, sys\n"
    if global_seed is not None:
        code += f"import numpy as np\nnp.random.seed({global_seed})\n"
    code += f"sys.argv = [{module!r}, *sys.argv[1:]]\nrunpy.run_module({module!r}, run_name=\"__main__\")\n"
    return subprocess.run([sys.executable, "-c", code, *args], capture_output=True, text=True, timeout=120)


def test_even_odds_give_log_two():
    assert binary_cross_entropy([0.5, 0.5], [0, 1]) == pytest.approx(math.log(2))


def test_known_value_without_smoothing():
    assert binary_cross_entropy([0.9], [1]) == pytest.approx(-math.log(0.9))


def test_known_value_with_smoothing():
    # target becomes 1 * (1 - 0.2) + 0.2 / 2 = 0.9
    expected = -(0.9 * math.log(0.9) + 0.1 * math.log(0.1))
    assert binary_cross_entropy([0.9], [1], label_smoothing=0.2) == pytest.approx(expected)


def test_smoothing_leaves_even_odds_unchanged():
    assert binary_cross_entropy([0.5], [1], label_smoothing=0.3) == pytest.approx(math.log(2))


@pytest.mark.parametrize("bad", [-0.1, 1.5])
def test_rejects_smoothing_outside_unit_interval(bad):
    with pytest.raises(ValueError):
        binary_cross_entropy([0.5], [1], label_smoothing=bad)


def _history(**kwargs):
    np.random.seed(0)  # noqa: NPY002 - the fixture shuffles with the global state
    return train(seed=0, steps=5, **kwargs)["history"]


def test_train_with_zero_smoothing_matches_default():
    assert _history(label_smoothing=0.0) == _history()


def test_train_with_smoothing_changes_the_loss():
    assert _history(label_smoothing=0.3) != _history()


def test_pipeline_flag_reaches_training():
    plain = run_cli("--steps", "1", "--label-smoothing", "0.0", global_seed=0)
    again = run_cli("--steps", "1", "--label-smoothing", "0.0", global_seed=0)
    smoothed = run_cli("--steps", "1", "--label-smoothing", "0.3", global_seed=0)
    assert plain.returncode == smoothed.returncode == 0, plain.stderr + smoothed.stderr
    assert plain.stdout == again.stdout
    assert plain.stdout != smoothed.stdout


def test_pipeline_rejects_smoothing_outside_unit_interval():
    assert run_cli("--steps", "1", "--label-smoothing", "1.5").returncode != 0
