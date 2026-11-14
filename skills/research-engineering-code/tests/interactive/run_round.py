"""Run a round of interactive episodes: cases x variants x repetitions, then check and judge each.

Everything lands under --out, which should be a durable directory outside this repository
(a temporary folder can be cleared before the results are read):

    OUT/plugins/<variant>/            clean plugin copies; tests/ is never included
    OUT/runs/<case>/<variant>/r<k>/   the agent's workspace (a fresh fixture copy)
    OUT/episodes/<case>-<variant>-r<k>/
        transcript.jsonl simulator.jsonl permissions.jsonl conversation.md metrics.json
        check.json   from ../check_run.py
        judge.json   from judge.py

Episodes that already have metrics.json, check.json or judge.json skip that stage, so an
interrupted round can be resumed by running the same command again. Episodes run one at a
time. Example:

    python run_round.py --out ~/eval-rounds/2026-11-14 --cases c09i-config-runner,c03i-seed-bug \
        --variants baseline,current --reps 3
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TESTS = HERE.parent
SKILL = TESTS.parent
VARIANT_SOURCES = {
    "current": SKILL,
    "previous-0.4.3": TESTS / "variants" / "previous-0.4.3",
    "previous-0.4.2": TESTS / "variants" / "previous-0.4.2",
    "previous-0.4.1": TESTS / "variants" / "previous-0.4.1",
    "previous-0.4.0": TESTS / "variants" / "previous-0.4.0",
    "previous-0.3.0": TESTS / "variants" / "previous-0.3.0",
    "previous-0.2.0": TESTS / "variants" / "previous-0.2.0",
    "previous-0.1.0": TESTS / "variants" / "previous-0.1.0",
}
PLUGIN_EXCLUDE = shutil.ignore_patterns("tests", "__pycache__", ".pytest_cache", ".ruff_cache", ".DS_Store")
UV = ["uv", "run", "--quiet", "--no-project"]


def build_plugin(variant: str, out: Path) -> Path | None:
    """Copy a variant into OUT/plugins without its evaluation material; None for the baseline."""
    if variant == "baseline":
        return None
    target = out / "plugins" / variant
    if not target.exists():
        shutil.copytree(VARIANT_SOURCES[variant], target, ignore=PLUGIN_EXCLUDE)
        # Snapshots keep their skill as SKILL.variant.md so the repository holds exactly one SKILL.md.
        if (target / "SKILL.variant.md").exists():
            (target / "SKILL.variant.md").rename(target / "SKILL.md")
        manifest = target / ".claude-plugin" / "plugin.json"
        if not manifest.exists():  # snapshots keep only the skill text, references and assets
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({"name": "research-engineering-code", "version": variant, "skills": ["./"]}))
    return target


def prepare_workspace(fixture: str, workspace: Path) -> None:
    """Fresh fixture copy, committed, with the fixture's environment ready."""
    if workspace.exists():
        return
    workspace.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(TESTS / "fixtures" / fixture, workspace)
    git = ["git", "-c", "user.name=eval", "-c", "user.email=eval@localhost"]
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    subprocess.run(["git", "add", "-A"], cwd=workspace, check=True)
    subprocess.run([*git, "commit", "-qm", "fixture"], cwd=workspace, check=True)
    (workspace / ".git" / "info" / "exclude").write_text(".venv/\nbuild/\n*.egg-info/\n__pycache__/\n.pytest_cache/\n")
    if fixture == "tinylab":
        python = workspace / ".venv" / "bin" / "python"
        subprocess.run(["uv", "venv", "-q", ".venv", "--python", "3.12"], cwd=workspace, check=True)
        subprocess.run(["uv", "pip", "install", "-q", "--python", str(python), "numpy", "pytest", "matplotlib"], cwd=workspace, check=True)
        subprocess.run(["uv", "pip", "install", "-q", "--python", str(python), "-e", "."], cwd=workspace, check=True)


def stage(label: str, command: list[str], output: Path, cwd: Path) -> bool:
    if output.exists():
        print(f"  {label}: already done")
        return True
    with (output.parent / f"{output.stem}.log").open("w") as log:
        done = subprocess.run(command, cwd=cwd, stdout=subprocess.PIPE, stderr=log, text=True, check=False)
    if done.returncode == 0 and done.stdout.strip():
        if output.suffix == ".json" and not output.exists():
            output.write_text(done.stdout)
        print(f"  {label}: ok")
        return True
    print(f"  {label}: FAILED (exit {done.returncode}); see {output.parent / (output.stem + '.log')}")
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cases", required=True, help="comma-separated ids from cases.json")
    parser.add_argument("--variants", default="baseline,current")
    parser.add_argument("--reps", type=int, default=3)
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--simulator-model", default="sonnet")
    parser.add_argument("--judge-model", default="sonnet")
    parser.add_argument("--budget", type=float, default=4.0, help="executor budget per episode in USD")
    parser.add_argument("--skip-judge", action="store_true")
    args = parser.parse_args()

    out = args.out.expanduser().resolve()
    if out == SKILL or SKILL in out.parents:
        sys.exit("--out must be outside the skill directory, or the agent's plugin copy could include results")
    cases = json.loads((HERE / "cases.json").read_text())
    for case_id in args.cases.split(","):
        case = cases[case_id]
        for variant in args.variants.split(","):
            plugin = build_plugin(variant, out)
            for rep in range(1, args.reps + 1):
                name = f"{case_id}-{variant}-r{rep}"
                print(name)
                workspace = out / "runs" / case_id / variant / f"r{rep}" / case["fixture"]
                episode = out / "episodes" / name
                if not (episode / "metrics.json").exists():
                    # A half-finished episode is rerun from scratch: its evidence and its workspace both go,
                    # so the new session starts from the fixture rather than the previous attempt's edits.
                    shutil.rmtree(episode, ignore_errors=True)
                    shutil.rmtree(workspace, ignore_errors=True)
                prepare_workspace(case["fixture"], workspace)
                if not (episode / "metrics.json").exists():
                    command = [*UV, "--with", "claude-agent-sdk", "python", "-B", str(HERE / "run_interactive.py"),
                               "--case", case_id, "--variant", variant, "--workspace", str(workspace), "--out", str(episode),
                               "--model", args.model, "--simulator-model", args.simulator_model, "--budget", str(args.budget)]
                    if plugin:
                        command += ["--plugin", str(plugin)]
                    episode.parent.mkdir(parents=True, exist_ok=True)
                    log = out / "episodes" / f"{name}.log"
                    with log.open("w") as handle:
                        done = subprocess.run(command, cwd=HERE, stdout=handle, stderr=subprocess.STDOUT, check=False)
                    print(f"  episode: {'ok' if done.returncode == 0 else f'FAILED (exit {done.returncode}); see {log}'}")
                    if done.returncode != 0:
                        continue
                else:
                    print("  episode: already done")
                stage("check", [*UV, "--with", "pytest", "--with", "numpy", "--with", "ruff", "python", "-B",
                                str(TESTS / "check_run.py"), "--case", case_id, "--workspace", str(workspace),
                                "--ruff-config", str(SKILL / "assets" / "python" / "pyproject-snippet.toml")],
                      episode / "check.json", TESTS)
                if not args.skip_judge:
                    stage("judge", [*UV, "--with", "claude-agent-sdk", "python", "-B", str(HERE / "judge.py"),
                                    "--case", case_id, "--episode", str(episode), "--workspace", str(workspace),
                                    "--model", args.judge_model],
                          episode / "judge.json", HERE)
    print(f"\nSummarise with: python {HERE / 'summarize.py'} {out}")


if __name__ == "__main__":
    main()
