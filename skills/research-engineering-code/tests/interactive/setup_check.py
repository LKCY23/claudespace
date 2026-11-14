"""Check the skill's project setup step and its report hint.

Five short sessions on a fixture copy with only the plugin under test loaded:

- new-file: no instruction file; the user asks for setup. CLAUDE.md must appear holding the rule.
- append:   a committed CLAUDE.md with other content; the rule must be appended and the rest kept.
- present:  CLAUDE.md already holds the rule; nothing may change.
- hint:     no instruction file; an ordinary task with the skill invoked by name (without the rule it often does
            not load on its own). The report must mention setup, and no instruction file may be created.
- no-hint:  CLAUDE.md holds the rule; the same task. The report must not mention setup.

A CLAUDE.md present at the start loads as project instructions. Every scenario also requires that the
skill was loaded, so none can pass without exercising it.

    uv run --no-project --with claude-agent-sdk python setup_check.py --out DIR [--only new-file,append]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import shutil
import subprocess
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)
from run_round import build_plugin, prepare_workspace

HERE = Path(__file__).resolve().parent
RULE_KEY = "load the research-engineering-code skill and follow it"
EXISTING = "# tinylab\n\nRun the tests with `python -m pytest`.\n"
SETUP = "Use the research-engineering-code skill: set it up for this project."
TASK = json.loads((HERE / "cases.json").read_text())["c10i-empty-accuracy"]["prompt"]
MENTIONS_SETUP = re.compile(r"not set up|set it up|set up for this project", re.IGNORECASE)
BLOCKED = re.compile(r"\b(pip|uv|npm|brew)\s+(install|add)\b|\bcurl\b|\bwget\b|\bgit\s+push\b|\bsudo\b")
SCENARIOS = {  # name: (instruction file at start, prompt)
    "new-file": (None, SETUP),
    "append": (EXISTING, SETUP),
    "present": (None, SETUP),  # filled with the rule from the skill below
    "hint": (None, "Use the research-engineering-code skill for this.\n\n" + TASK),  # without the rule it may not load unasked
    "no-hint": (None, TASK),  # likewise
}


def rule_from(plugin: Path) -> str:
    """The rule paragraph, read from the skill so this check cannot drift from it."""
    return next(line for line in (plugin / "SKILL.md").read_text().splitlines() if RULE_KEY in line)


def guard(workspace: Path):
    async def can_use_tool(tool_name, tool_input, context):
        if tool_name in {"Edit", "Write"} and not Path(tool_input.get("file_path", "")).resolve().is_relative_to(workspace):
            return PermissionResultDeny(message="Only files inside the project may be changed.")
        if tool_name == "Bash" and BLOCKED.search(tool_input.get("command", "")):
            return PermissionResultDeny(message="No installs or network access in this session.")
        return PermissionResultAllow()
    return can_use_tool


async def session(prompt: str, workspace: Path, plugin: Path, model: str) -> dict:
    """One session. A CLAUDE.md in the workspace loads as project instructions, as it would in real use."""
    sources = ["project"] if (workspace / "CLAUDE.md").exists() else []
    options = ClaudeAgentOptions(cwd=str(workspace), model=model, strict_mcp_config=True, setting_sources=sources,
                                 plugins=[{"type": "local", "path": str(plugin)}], cli_path=shutil.which("claude"),
                                 can_use_tool=guard(workspace), permission_mode="default", max_turns=40, max_budget_usd=1.0)
    texts, skills, cost = [], [], 0.0
    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                texts += [b.text for b in message.content if isinstance(b, TextBlock)]
                skills += [str(b.input.get("skill", "")) for b in message.content if isinstance(b, ToolUseBlock) and b.name == "Skill"]
            if isinstance(message, ResultMessage):
                cost += message.total_cost_usd or 0.0
    except Exception as error:  # noqa: BLE001 - a turn or budget limit ends the session; the checks below still apply
        texts.append(f"[stopped: {str(error)[:120]}]")
    return {"final_text": texts[-1] if texts else "", "all_text": "\n".join(texts), "skill_loaded": any("research-engineering-code" in s for s in skills),
            "cost_usd": round(cost, 4)}


def changed_files(workspace: Path) -> list[str]:
    lines = subprocess.run(["git", "status", "--porcelain"], cwd=workspace, capture_output=True, text=True, check=True).stdout.splitlines()
    return sorted(line[3:] for line in lines if not line[3:].startswith((".venv", "build", ".pytest_cache")) and "__pycache__" not in line)


def verdict(name: str, start: str | None, workspace: Path, outcome: dict) -> dict:
    claude, agents = workspace / "CLAUDE.md", workspace / "AGENTS.md"
    now = claude.read_text() if claude.exists() else None
    changed, text = changed_files(workspace), outcome["all_text"]
    if name == "new-file":
        checks = {"CLAUDE.md created with the rule": now is not None and RULE_KEY in now, "nothing else changed": changed == ["CLAUDE.md"],
                  "added lines shown to the user": RULE_KEY in text}
    elif name == "append":
        checks = {"rule appended": now is not None and now.count(RULE_KEY) == 1, "existing lines kept": now is not None and now.startswith(start),
                  "nothing else changed": changed == ["CLAUDE.md"], "collaborators and CLAUDE.local.md mentioned": "CLAUDE.local.md" in text}
    elif name == "present":
        checks = {"file unchanged": now == start, "nothing changed": changed == [], "says it is already set up": "already" in text.lower()}
    elif name == "hint":
        checks = {"no instruction file created": not claude.exists() and not agents.exists(),
                  "report mentions setup": bool(MENTIONS_SETUP.search(outcome["final_text"]))}
    else:
        checks = {"instruction file unchanged": now == start, "report does not mention setup": not MENTIONS_SETUP.search(outcome["final_text"])}
    checks["skill loaded"] = outcome["skill_loaded"]  # without it a scenario could pass without testing the skill
    return {"scenario": name, "passed": all(checks.values()), "checks": checks, "changed_files": changed, "cost_usd": outcome["cost_usd"]}


def prepare(name: str, out: Path, rule: str) -> tuple[str | None, Path]:
    """A committed fixture copy holding the scenario's starting instruction file, if it has one."""
    start = EXISTING + "\n" + rule + "\n" if name in {"present", "no-hint"} else SCENARIOS[name][0]
    workspace = out / "runs" / name / "tinylab"
    prepare_workspace("tinylab", workspace)
    if start is not None:
        (workspace / "CLAUDE.md").write_text(start)
        git = ["git", "-c", "user.name=eval", "-c", "user.email=eval@localhost"]
        subprocess.run(["git", "add", "CLAUDE.md"], cwd=workspace, check=True)
        subprocess.run([*git, "commit", "-qm", "instructions"], cwd=workspace, check=True)
    return start, workspace


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--only", default=",".join(SCENARIOS))
    args = parser.parse_args()
    out = args.out.resolve()
    if HERE.parent.parent in out.parents:
        raise SystemExit("--out must be outside the skill folder")
    plugin = build_plugin("current", out)
    rule = rule_from(plugin)
    results = []
    for name in args.only.split(","):
        start, workspace = prepare(name, out, rule)
        prompt = SCENARIOS[name][1]
        outcome = await session(prompt, workspace, plugin, args.model)
        (out / f"{name}.txt").write_text(outcome["all_text"])
        results.append(verdict(name, start, workspace, outcome))
        print(json.dumps(results[-1], ensure_ascii=False))
    (out / "setup_check.json").write_text(json.dumps(results, indent=1, ensure_ascii=False))
    print(f"passed {sum(r['passed'] for r in results)}/{len(results)}, cost ${sum(r['cost_usd'] for r in results):.2f}")


if __name__ == "__main__":
    asyncio.run(main())
