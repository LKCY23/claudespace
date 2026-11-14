"""Hidden acceptance test for case h01. Never shown to the executor."""

import re
import subprocess
import sys

import pytest

from tinylab.metrics import macro_f1


def run_cli(*args, module="tinylab.train", global_seed=None):
    """Run a module as a script in a fresh interpreter, optionally fixing the global NumPy seed first."""
    code = "import runpy, sys\n"
    if global_seed is not None:
        code += f"import numpy as np\nnp.random.seed({global_seed})\n"
    code += f"sys.argv = [{module!r}, *sys.argv[1:]]\nrunpy.run_module({module!r}, run_name=\"__main__\")\n"
    return subprocess.run([sys.executable, "-c", code, *args], capture_output=True, text=True, timeout=120)


def test_known_value_two_classes():
    # class 0: precision 1/2, recall 1 -> F1 2/3; class 1: precision 1, recall 2/3 -> F1 4/5
    assert macro_f1([0, 0, 1, 1], [0, 1, 1, 1], num_classes=2) == pytest.approx((2 / 3 + 4 / 5) / 2)


def test_perfect_predictions_give_one():
    assert macro_f1([0, 1, 2], [0, 1, 2], num_classes=3) == pytest.approx(1.0)


def test_absent_class_contributes_zero():
    assert macro_f1([0, 1], [0, 1], num_classes=3) == pytest.approx(2 / 3)


def test_length_mismatch_raises():
    with pytest.raises(ValueError):
        macro_f1([0, 1], [0], num_classes=2)


def test_pipeline_reports_f1_next_to_accuracy():
    done = run_cli("--seed", "0", "--steps", "20")
    assert done.returncode == 0, done.stderr
    report = done.stdout + done.stderr
    assert re.search(r"f1\W*\d", report, re.IGNORECASE)
    assert re.search(r"accuracy\W*\d", report, re.IGNORECASE)
