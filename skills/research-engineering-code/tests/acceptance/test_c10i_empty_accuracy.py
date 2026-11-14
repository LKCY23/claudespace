"""Hidden acceptance test for interactive case c10i. Never shown to the executor.

Test names carry their category:
- other names       what the request asks for (required); test_pipeline_* go through the real entry point
- test_protection_* checks the request does not name but whose absence lets a wrong result through silently
- test_existing_*   existing behaviour the request gives no reason to change
"""

import warnings

import pytest

from tinylab.metrics import accuracy


def test_empty_input_raises_instead_of_returning_nan():
    # The request says "fail loudly": any raised error counts; a returned value does not.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with pytest.raises(Exception):  # noqa: B017, PT011
            accuracy([], [])


def test_existing_non_empty_accuracy_unchanged():
    assert accuracy([1, 0, 1, 1], [1, 1, 1, 0]) == 0.5
