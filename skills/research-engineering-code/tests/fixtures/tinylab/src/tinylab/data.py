"""Synthetic data and batching."""

import numpy as np


def make_blobs(n_samples, seed):
    """Return (features, labels) for two Gaussian blobs in 2D."""
    rng = np.random.default_rng(seed)
    half = n_samples // 2
    x0 = rng.normal(loc=-1.0, scale=1.0, size=(half, 2))
    x1 = rng.normal(loc=1.0, scale=1.0, size=(n_samples - half, 2))
    x = np.concatenate([x0, x1])
    y = np.concatenate([np.zeros(half, dtype=int), np.ones(n_samples - half, dtype=int)])
    return x, y


def iterate_batches(x, y, batch_size, seed):
    """Yield shuffled mini-batches forever."""
    idx = np.arange(len(x))
    while True:
        np.random.shuffle(idx)
        for start in range(0, len(idx), batch_size):
            batch = idx[start:start + batch_size]
            yield x[batch], y[batch]
