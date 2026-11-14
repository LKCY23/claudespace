"""Train logistic regression on blobs."""

import argparse

import numpy as np

from tinylab.data import iterate_batches, make_blobs
from tinylab.metrics import accuracy


def train(seed=0, steps=200, lr=0.1, batch_size=16, n_samples=200):
    x, y = make_blobs(n_samples, seed)
    rng = np.random.default_rng(seed)
    w = rng.normal(scale=0.01, size=2)
    b = 0.0
    batches = iterate_batches(x, y, batch_size, seed)
    history = []
    for step in range(steps):
        xb, yb = next(batches)
        z = xb @ w + b
        p = 1.0 / (1.0 + np.exp(-z))
        loss = -np.mean(yb * np.log(p + 1e-12) + (1 - yb) * np.log(1 - p + 1e-12))
        grad_z = (p - yb) / len(yb)
        w = w - lr * (xb.T @ grad_z)
        b = b - lr * grad_z.sum()
        history.append(float(loss))
        if step % 50 == 0:
            print(f"step {step} loss {loss:.4f}")
    preds = ((x @ w + b) > 0).astype(int)
    acc = accuracy(preds, y)
    print(f"final accuracy {acc:.3f}")
    return {"history": history, "accuracy": acc, "w": w, "b": b}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--lr", type=float, default=0.1)
    args = parser.parse_args()
    train(seed=args.seed, steps=args.steps, lr=args.lr)
