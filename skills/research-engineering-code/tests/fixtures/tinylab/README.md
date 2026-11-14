# tinylab

Logistic regression on synthetic two-class blobs. Small enough to run in a
second on a laptop CPU.

    python -m pytest -q
    python -m tinylab.train --seed 0 --steps 200

`train` prints the loss every 50 steps and the final accuracy.
