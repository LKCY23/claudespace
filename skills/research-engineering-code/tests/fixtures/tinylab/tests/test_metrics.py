from tinylab.metrics import accuracy


def test_accuracy_counts_matching_predictions():
    assert accuracy([1, 0, 1, 1], [1, 1, 1, 0]) == 0.5
