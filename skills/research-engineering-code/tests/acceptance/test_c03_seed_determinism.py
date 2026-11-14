"""Hidden acceptance test for case c03. Never shown to the executor.

Not checked here, left to the judge: whether batches are still shuffled.
Removing the shuffle would also make runs repeat.
"""

import subprocess
import sys

import numpy as np

from tinylab.train import train


def run_cli(*args, module="tinylab.train", global_seed=None):
    """Run a module as a script in a fresh interpreter, optionally fixing the global NumPy seed first."""
    code = "import runpy, sys\n"
    if global_seed is not None:
        code += f"import numpy as np\nnp.random.seed({global_seed})\n"
    code += f"sys.argv = [{module!r}, *sys.argv[1:]]\nrunpy.run_module({module!r}, run_name=\"__main__\")\n"
    return subprocess.run([sys.executable, "-c", code, *args], capture_output=True, text=True, timeout=120)


def test_same_seed_gives_identical_history():
    assert train(seed=0, steps=40)["history"] == train(seed=0, steps=40)["history"]


def test_different_seeds_give_different_history():
    assert train(seed=0, steps=40)["history"] != train(seed=1, steps=40)["history"]


def test_history_does_not_depend_on_global_numpy_state():
    np.random.seed(1)  # noqa: NPY002
    first = train(seed=0, steps=40)["history"]
    np.random.seed(2)  # noqa: NPY002
    second = train(seed=0, steps=40)["history"]
    assert first == second


def test_training_leaves_global_numpy_state_alone():
    # Reseeding the global generator inside train would pass the tests above but
    # silently reset every other user of np.random.
    np.random.seed(5)  # noqa: NPY002
    before = np.random.get_state()  # noqa: NPY002
    train(seed=0, steps=40)
    after = np.random.get_state()  # noqa: NPY002
    np.testing.assert_array_equal(before[1], after[1])
    assert before[2] == after[2]


def test_pipeline_two_runs_with_one_seed_print_the_same():
    first = run_cli("--seed", "0", "--steps", "60")
    second = run_cli("--seed", "0", "--steps", "60")
    other = run_cli("--seed", "1", "--steps", "60")
    assert first.returncode == 0, first.stderr
    assert first.stdout == second.stdout
    assert first.stdout != other.stdout
