"""Hidden acceptance test for case h03. Never shown to the executor."""

import subprocess
import sys

import numpy as np
import pytest

from tinylab.checkpoint import load_checkpoint, save_checkpoint
from tinylab.data import make_blobs


def run_cli(*args, module="tinylab.train", global_seed=None):
    """Run a module as a script in a fresh interpreter, optionally fixing the global NumPy seed first."""
    code = "import runpy, sys\n"
    if global_seed is not None:
        code += f"import numpy as np\nnp.random.seed({global_seed})\n"
    code += f"sys.argv = [{module!r}, *sys.argv[1:]]\nrunpy.run_module({module!r}, run_name=\"__main__\")\n"
    return subprocess.run([sys.executable, "-c", code, *args], capture_output=True, text=True, timeout=120)


def test_round_trip_returns_equal_state(tmp_path):
    path = tmp_path / "ckpt.npz"
    save_checkpoint(path, w=np.array([0.5, -1.5]), b=0.25, step=7)
    state = load_checkpoint(path)
    np.testing.assert_array_equal(state["w"], np.array([0.5, -1.5]))
    assert float(state["b"]) == 0.25
    assert int(state["step"]) == 7


def test_missing_checkpoint_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_checkpoint(tmp_path / "absent.npz")


def test_pipeline_resume_uses_checkpoint_weights(tmp_path):
    w, b = np.array([-1.0, -1.0]), 0.0  # points the wrong way: far from any fresh start
    path = tmp_path / "ckpt.npz"
    save_checkpoint(path, w=w, b=b, step=0)
    x, y = make_blobs(200, seed=0)
    expected = float((((x @ w + b) > 0).astype(int) == y).mean())
    done = run_cli("--seed", "0", "--steps", "0", "--resume", str(path))
    assert done.returncode == 0, done.stderr
    assert f"{expected:.3f}" in done.stdout + done.stderr


def test_pipeline_missing_resume_path_fails(tmp_path):
    assert run_cli("--steps", "0", "--resume", str(tmp_path / "absent.npz")).returncode != 0
