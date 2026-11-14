"""Hidden acceptance test for case c04. Never shown to the executor."""

import logging
import subprocess
import sys

import pytest

from tinylab.logging_utils import configure_logging, get_logger
from tinylab.train import train


def run_cli(*args, module="tinylab.train", global_seed=None):
    """Run a module as a script in a fresh interpreter, optionally fixing the global NumPy seed first."""
    code = "import runpy, sys\n"
    if global_seed is not None:
        code += f"import numpy as np\nnp.random.seed({global_seed})\n"
    code += f"sys.argv = [{module!r}, *sys.argv[1:]]\nrunpy.run_module({module!r}, run_name=\"__main__\")\n"
    return subprocess.run([sys.executable, "-c", code, *args], capture_output=True, text=True, timeout=120)


class _Collect(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture(autouse=True)
def _restore_tinylab_logger():
    logger = logging.getLogger("tinylab")
    level, handlers, propagate = logger.level, list(logger.handlers), logger.propagate
    yield
    logger.setLevel(level)
    logger.propagate = propagate
    logger.handlers[:] = handlers


def test_loggers_live_under_package_namespace():
    assert get_logger("trainer").name == "tinylab.trainer"


def test_configure_sets_level():
    configure_logging("DEBUG")
    assert logging.getLogger("tinylab").level == logging.DEBUG


def test_configuring_twice_does_not_duplicate_handlers():
    configure_logging("INFO")
    count = len(logging.getLogger("tinylab").handlers)
    configure_logging("INFO")
    assert len(logging.getLogger("tinylab").handlers) == count


def test_unknown_level_raises():
    with pytest.raises(ValueError):
        configure_logging("LOUD")


def test_train_no_longer_prints(capsys):
    train(seed=0, steps=5)
    assert capsys.readouterr().out == ""


def test_train_progress_goes_to_package_loggers():
    # Deleting the prints without logging anything would pass the test above.
    configure_logging("DEBUG")
    collector = _Collect()
    logging.getLogger("tinylab").addHandler(collector)
    train(seed=0, steps=60)
    assert any(record.name.startswith("tinylab") for record in collector.records)


def test_pipeline_accepts_log_level_flag():
    done = run_cli("--steps", "5", "--log-level", "DEBUG")
    assert done.returncode == 0, done.stderr


def test_pipeline_rejects_unknown_log_level():
    assert run_cli("--steps", "5", "--log-level", "LOUD").returncode != 0
