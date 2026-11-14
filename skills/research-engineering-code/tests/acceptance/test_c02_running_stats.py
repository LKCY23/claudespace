"""Hidden acceptance test for case c02. Never shown to the executor."""

import math

import pytest

from tinylab.stats import RunningStats
from tinylab.train import train


def test_mean_std_count_for_known_values():
    stats = RunningStats()
    for value in (1.0, 2.0, 3.0, 4.0):
        stats.update(value)
    assert stats.count == 4
    assert stats.mean == pytest.approx(2.5)
    assert stats.std == pytest.approx(math.sqrt(1.25))


def test_single_value_has_zero_std():
    stats = RunningStats()
    stats.update(7.0)
    assert stats.mean == pytest.approx(7.0)
    assert stats.std == pytest.approx(0.0)


def test_reading_before_any_update_raises():
    with pytest.raises(ValueError):
        RunningStats().mean  # noqa: B018


def test_train_reports_loss_mean_matching_history():
    result = train(seed=0, steps=20)
    assert result["loss_mean"] == pytest.approx(sum(result["history"]) / 20)
    assert result["loss_std"] >= 0.0
