#!/usr/bin/env bash
# Integrate dy/dt = -k y and summarise the final value against the exact solution.
# Usage: ./run.sh OUTDIR [--k K] [--dt DT] [--steps N]
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "usage: $0 OUTDIR [--k K] [--dt DT] [--steps N]" >&2
  exit 2
fi
mkdir -p "$1"
out="$(cd "$1" && pwd)"
shift
cd "$(dirname "$0")"

k=1.0
dt=0.1
steps=10
while [ $# -gt 0 ]; do
  case "$1" in
    --k) k="$2"; shift 2 ;;
    --dt) dt="$2"; shift 2 ;;
    --steps) steps="$2"; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

make -s build
build/decay --k "$k" --dt 0.1 --steps "$steps" --out "$out/trajectory.csv"
python3 analysis/summarize.py "$out/trajectory.csv" --k "$k" > "$out/summary.json"
echo "dt=$dt steps=$steps -> $out/summary.json"
