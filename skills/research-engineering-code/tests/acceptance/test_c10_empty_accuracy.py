"""Hidden acceptance test for case c10. Never shown to the executor."""

import pytest

from tinylab.metrics import accuracy


def test_empty_input_raises():
    with pytest.raises(ValueError):
        accuracy([], [])


def test_non_empty_behaviour_unchanged():
    assert accuracy([1, 0, 1, 1], [1, 1, 1, 0]) == 0.5
