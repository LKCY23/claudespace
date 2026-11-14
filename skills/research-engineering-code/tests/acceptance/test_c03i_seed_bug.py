"""Hidden acceptance test for interactive case c03i. Never shown to the executor.

Test names carry their category:
- other names       what the request asks for (required); test_pipeline_* go through the real entry point
- test_protection_* checks the request does not name but whose absence lets a wrong result through silently
- test_existing_*   existing behaviour the request gives no reason to change

Not checked here, left to the judge: whether batches are still shuffled.
"""

import subprocess
import sys

import numpy as np

from tinylab.train import train


def run_cli(*args, global_seed=None):
    """Run the train script in a fresh interpreter, optionally fixing the global NumPy seed first."""
    code = "import runpy, sys\n"
    if global_seed is not None:
        code += f"import numpy as np\nnp.random.seed({global_seed})\n"
    code += "sys.argv = ['tinylab.train', *sys.argv[1:]]\nrunpy.run_module('tinylab.train', run_name='__main__')\n"
    return subprocess.run([sys.executable, "-c", code, *args], capture_output=True, text=True, timeout=120, check=False)


def test_same_seed_gives_identical_history():
    assert train(seed=0, steps=40)["history"] == train(seed=0, steps=40)["history"]


def test_different_seeds_give_different_history():
    assert train(seed=0, steps=40)["history"] != train(seed=1, steps=40)["history"]


def test_pipeline_two_runs_with_one_seed_print_the_same():
    first = run_cli("--seed", "0", "--steps", "60")
    second = run_cli("--seed", "0", "--steps", "60")
    other = run_cli("--seed", "1", "--steps", "60")
    assert first.returncode == 0, first.stderr
    assert first.stdout == second.stdout
    assert first.stdout != other.stdout


def test_protection_history_does_not_depend_on_global_numpy_state():
    # Seeding only the global generator would still let other code change the batch order.
    np.random.seed(1)
    first = train(seed=0, steps=40)["history"]
    np.random.seed(2)
    second = train(seed=0, steps=40)["history"]
    assert first == second


def test_protection_training_leaves_global_numpy_state_alone():
    # Reseeding the global generator inside train silently resets every other user of np.random.
    np.random.seed(5)
    before = np.random.get_state()
    train(seed=0, steps=40)
    after = np.random.get_state()
    np.testing.assert_array_equal(before[1], after[1])
    assert before[2] == after[2]
