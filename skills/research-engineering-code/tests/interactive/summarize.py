"""Summarise a round: one row per episode, then case x variant means, as Markdown.

    python summarize.py OUT [--csv OUT/summary.csv]

Columns:
- req: required hidden tests passed / total (what the request names)
- prot: protection tests passed / total (checks the request does not name)
- exist: existing-behaviour tests passed / total
- design: judge, design written before the first edit (1/0); plan: characters of agent text before the first edit
- struct, read: judge scores 1-5 for structure and readability
- caps: capabilities in the final code the workflow does not need; removed: built and then removed on objection
- noname: protections for which no wrong result can be named
- fixes: corrections the researcher had to make; asks: question-tool calls
- tests: tests added; mut: mutation score among mutants the hidden tests can see
- leak: simulated-user replies the judge flagged; cost: executor + simulated user, USD
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from pathlib import Path

COLUMNS = ["episode", "case", "variant", "req", "prot", "exist", "design", "plan", "struct", "read", "caps", "removed",
           "noname", "fixes", "asks", "tests", "mut", "leak", "cost"]
NAME = re.compile(r"^(?P<case>.+?)-(?P<variant>baseline|current|previous-[\d.]+)-r(?P<rep>\d+)$")
NUMERIC = ["req", "prot", "exist", "design", "plan", "struct", "read", "caps", "removed", "noname", "fixes", "asks",
           "tests", "mut", "leak", "cost"]
FRACTIONS = ("req", "prot", "exist")


def fraction(group: dict | None) -> str:
    return f"{group['passed']}/{group['total']}" if group and group.get("total") else ""


def as_number(value):
    """A 'passed/total' cell becomes its ratio, so group means are comparable."""
    if isinstance(value, str) and "/" in value:
        passed, total = value.split("/")
        return int(passed) / int(total) if int(total) else None
    return value if isinstance(value, (int, float)) else None


def load(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def row(episode: Path) -> dict:
    metrics, check, judge = load(episode / "metrics.json"), load(episode / "check.json"), load(episode / "judge.json")
    match = NAME.match(episode.name)
    case, variant = (match["case"], match["variant"]) if match else (episode.name, "?")
    acceptance = check.get("acceptance") or {}
    mutation = check.get("mutation") or {}
    decisions = metrics.get("turn_end_decisions", [])

    def verdict(key):
        value = (judge.get(key) or {}).get("verdict")
        return None if value is None else int(value == "pass")

    def count(key):
        return len(judge.get(key, [])) if judge else None

    return {
        "episode": episode.name, "case": case, "variant": variant,
        "req": fraction(acceptance.get("required")), "prot": fraction(acceptance.get("protections")),
        "exist": fraction(acceptance.get("existing")),
        "design": verdict("design_before_editing"),
        "plan": metrics.get("agent_text_chars_before_first_edit"),
        "struct": (judge.get("structure") or {}).get("score"),
        "read": (judge.get("readability") or {}).get("score"),
        "caps": count("unneeded_capabilities"), "removed": count("capabilities_built_then_removed"),
        "noname": count("protections_without_named_failure"),
        "fixes": sum(1 for d in decisions if d == "redirect") if metrics else None,
        "asks": metrics.get("ask_user_question_calls"),
        "tests": len((check.get("tests") or {}).get("added", [])) if check else None,
        "mut": mutation.get("score") if mutation.get("filtered_by_acceptance") else None,  # unfiltered rates are not comparable
        "leak": sum(1 for r in judge.get("simulator_replies", []) if r.get("ok") is False) if judge else None,
        "cost": round((metrics.get("executor_cost_usd") or 0) + (metrics.get("simulator_cost_usd") or 0), 3) if metrics else None,
    }


def table(rows: list[dict], columns: list[str]) -> str:
    def cell(value):
        return "" if value is None else (f"{value:.2f}" if isinstance(value, float) else str(value))
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    lines += ["| " + " | ".join(cell(r.get(c)) for c in columns) + " |" for r in rows]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out", type=Path)
    parser.add_argument("--csv", type=Path)
    args = parser.parse_args()
    episodes = sorted(p for p in (args.out / "episodes").iterdir() if p.is_dir())
    if not episodes:
        sys.exit("no episodes found")
    rows = [row(e) for e in episodes]
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        groups.setdefault((r["case"], r["variant"]), []).append(r)
    means = []
    for (case, variant), members in sorted(groups.items()):
        mean = {"case": case, "variant": variant, "n": len(members)}
        for column in NUMERIC:
            values = [v for v in (as_number(m[column]) for m in members) if v is not None]
            mean[column] = round(statistics.mean(values), 2) if values else None
        means.append(mean)
    print("## Means per case and variant\n")
    print(table(means, ["case", "variant", "n", *NUMERIC]))
    print("\n## Episodes\n")
    print(table(rows, COLUMNS))
    if args.csv:
        with args.csv.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    main()
