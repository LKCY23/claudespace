"""Hidden acceptance test for case c05. Never shown to the executor.

The request says behaviour must not change, so the loss history and the script
output for a fixed global NumPy state must equal those recorded from the
untouched fixture. These tests pass on the untouched fixture too; that the
code was actually restructured and tested is checked by the change record and
the judge, not here.
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

REFERENCE_HISTORY = [
    0.693488012681, 0.647365465805, 0.632936631761, 0.576236155835, 0.569153080402,
    0.493739726954, 0.506873254115, 0.482944159267, 0.515296760835, 0.441166729373,
    0.470507469059, 0.425139545034, 0.325796750528, 0.556718102838, 0.391916759218,
    0.387959762227, 0.426239225421, 0.400623127069, 0.453304421535, 0.371040394219,
]
REFERENCE_OUTPUT = "step 0 loss 0.6935\nstep 50 loss 0.3762\nfinal accuracy 0.890\n"


def test_history_matches_recorded_reference():
    np.random.seed(123)  # noqa: NPY002 - the fixture shuffles with the global state
    result = train(seed=0, steps=20)
    np.testing.assert_allclose(result["history"], REFERENCE_HISTORY, atol=1e-9)
    assert result["accuracy"] == 0.885


def test_pipeline_output_matches_recorded_reference():
    done = run_cli("--seed", "0", "--steps", "60", global_seed=123)
    assert done.returncode == 0, done.stderr
    assert done.stdout == REFERENCE_OUTPUT
