"""Evaluation metrics."""

import numpy as np


def accuracy(preds, labels):
    """Fraction of predictions equal to the labels."""
    preds = np.asarray(preds)
    labels = np.asarray(labels)
    return float((preds == labels).mean())
