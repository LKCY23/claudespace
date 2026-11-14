"""Hidden acceptance test for case h02. Never shown to the executor."""

import re
import subprocess
import sys

import numpy as np
import pytest

from tinylab.data import make_blobs, split_and_standardize


def run_cli(*args, module="tinylab.train", global_seed=None):
    """Run a module as a script in a fresh interpreter, optionally fixing the global NumPy seed first."""
    code = "import runpy, sys\n"
    if global_seed is not None:
        code += f"import numpy as np\nnp.random.seed({global_seed})\n"
    code += f"sys.argv = [{module!r}, *sys.argv[1:]]\nrunpy.run_module({module!r}, run_name=\"__main__\")\n"
    return subprocess.run([sys.executable, "-c", code, *args], capture_output=True, text=True, timeout=120)


def _split(seed):
    x, y = make_blobs(200, seed=0)
    return split_and_standardize(x, y, val_fraction=0.25, rng=np.random.default_rng(seed))


def test_sizes_follow_val_fraction():
    x_train, y_train, x_val, y_val = _split(0)
    assert (len(x_train), len(x_val)) == (150, 50)
    assert (len(y_train), len(y_val)) == (150, 50)


def test_training_features_are_standardized_with_their_own_statistics():
    x_train, _, _, _ = _split(0)
    np.testing.assert_allclose(x_train.mean(axis=0), 0.0, atol=1e-9)
    np.testing.assert_allclose(x_train.std(axis=0), 1.0, atol=1e-9)


def test_validation_features_use_training_statistics():
    _, _, x_val, _ = _split(0)
    # With its own statistics the validation mean would be exactly zero.
    assert np.abs(x_val.mean(axis=0)).max() > 1e-6


def test_rows_stay_paired_and_splits_are_disjoint():
    # Feature 0 encodes the row id. One shared positive affine map is applied to
    # both splits, so sorting the combined values recovers the original order.
    ids = np.arange(40, dtype=float)
    x = np.column_stack([ids, ids**2])
    y = ids.astype(int) % 2
    x_train, y_train, x_val, y_val = split_and_standardize(x, y, val_fraction=0.25, rng=np.random.default_rng(0))
    values = np.concatenate([x_train[:, 0], x_val[:, 0]])
    labels = np.concatenate([y_train, y_val])
    order = np.argsort(values)
    assert len(np.unique(np.round(values, 9))) == 40
    np.testing.assert_array_equal(labels[order], y)


def test_same_generator_seed_gives_same_split():
    first, second = _split(3), _split(3)
    for a, b in zip(first, second, strict=True):
        np.testing.assert_array_equal(a, b)


def test_rejects_val_fraction_outside_open_unit_interval():
    x, y = make_blobs(20, seed=0)
    with pytest.raises(ValueError):
        split_and_standardize(x, y, val_fraction=1.0, rng=np.random.default_rng(0))


def test_pipeline_reports_validation_accuracy():
    done = run_cli("--seed", "0", "--steps", "20")
    assert done.returncode == 0, done.stderr
    assert re.search(r"val\w*[ _-]*acc\w*\W*\d", done.stdout + done.stderr, re.IGNORECASE)
