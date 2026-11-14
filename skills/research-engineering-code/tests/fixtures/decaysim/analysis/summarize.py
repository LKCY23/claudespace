"""Compare the last point of a decay trajectory with the exact solution."""

import argparse
import csv
import json
import math
import sys


def read_trajectory(path):
    """Return the (t, y) rows of a trajectory CSV written by the simulator."""
    with open(path, newline="") as handle:
        rows = [(float(row["t"]), float(row["y"])) for row in csv.DictReader(handle)]
    if not rows:
        raise ValueError(f"{path} has no data rows")
    return rows


def summarize(trajectory, k):
    """Final value, exact value exp(-k t) at the same time, and their absolute difference."""
    final_t, final_y = trajectory[-1]
    exact_y = math.exp(-k * final_t)
    return {"final_t": final_t, "final_y": final_y, "exact_y": exact_y, "abs_error": abs(final_y - exact_y)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trajectory")
    parser.add_argument("--k", type=float, required=True)
    args = parser.parse_args(argv)
    json.dump(summarize(read_trajectory(args.trajectory), args.k), sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
