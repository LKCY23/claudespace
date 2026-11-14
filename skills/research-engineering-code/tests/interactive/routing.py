"""Routing test: does the skill load on its own for requests it should cover, and stay out otherwise?

Each prompt in routing_prompts.json starts a short, read-only session on a fixture copy with
only the plugin under test added (no user, project or local settings). With --user-setup the
user's own settings, plugins and skills load as well, which is closer to real use. With --project-rule
the given text is written to CLAUDE.md in the fixture copy and project instructions load too, to
measure whether a one-line pointer in a project's instructions routes better than the description
alone. The session may read
files and load skills; edits and shell commands are refused, and it stops after a few turns.
A prompt counts as triggered if the agent calls the Skill tool for the target.

    uv run --no-project --with claude-agent-sdk python routing.py --plugin PATH --out DIR [--reps 1]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import tempfile
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    SystemMessage,
    ToolUseBlock,
    query,
)

HERE = Path(__file__).resolve().parent
TARGET = "research-engineering-code"
READ_ONLY = {"Read", "Glob", "Grep", "Skill", "LS"}


async def refuse_changes(tool_name, tool_input, context):
    if tool_name in READ_ONLY:
        return PermissionResultAllow()
    return PermissionResultDeny(message="This is a read-only session; stop and summarise what you would do.")


async def probe(prompt: str, workspace: Path, plugin: Path, model: str, max_turns: int, user_setup: dict | None,
                project_rule: bool = False) -> dict:
    """One read-only session. With user_setup, the user's own settings, plugins and skills load too;
    with project_rule, the workspace's CLAUDE.md loads as project instructions."""
    sources = (["user"] if user_setup is not None else []) + (["project"] if project_rule else [])
    extra = {"setting_sources": sources} | ({"settings": json.dumps(user_setup)} if user_setup is not None else {})
    options = ClaudeAgentOptions(cwd=str(workspace), model=model, strict_mcp_config=True,
                                 plugins=[{"type": "local", "path": str(plugin)}], cli_path=shutil.which("claude"),
                                 can_use_tool=refuse_changes, permission_mode="default", max_turns=max_turns, **extra)
    tools, cost, stopped, listed = [], 0.0, "finished", None
    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, SystemMessage) and message.subtype == "init":
                listed = len(message.data.get("skills", []))
            if isinstance(message, AssistantMessage):
                tools += [(b.name, str(b.input.get("skill", ""))) for b in message.content if isinstance(b, ToolUseBlock)]
            if isinstance(message, ResultMessage):
                cost += message.total_cost_usd or 0.0
    except Exception as error:  # noqa: BLE001 - hitting max_turns raises; that is the intended stop
        stopped = f"stopped: {str(error)[:120]}"
    triggered = any(name == "Skill" and TARGET in skill for name, skill in tools)
    return {"triggered": triggered, "first_tools": [n for n, _ in tools[:5]], "cost_usd": round(cost, 4),
            "stopped": stopped, "skills_listed": listed}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--plugin", type=Path, required=True, help="clean plugin copy, without tests/")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--reps", type=int, default=1)
    parser.add_argument("--max-turns", type=int, default=4)
    parser.add_argument("--user-setup", action="store_true",
                        help="also load the user's own settings, plugins and skills, to measure routing among them")
    parser.add_argument("--disable-plugin", action="append", default=[],
                        help="with --user-setup: a plugin id to switch off for these sessions only (repeatable)")
    parser.add_argument("--project-rule", help="text written to CLAUDE.md in each fixture copy and loaded as project instructions")
    args = parser.parse_args()
    user_setup = {"enabledPlugins": dict.fromkeys(args.disable_plugin, False)} if args.user_setup else None
    if (args.plugin / "tests").exists():
        raise SystemExit("--plugin must not contain tests/; use the copy run_round.py builds under OUT/plugins")
    args.out.mkdir(parents=True, exist_ok=True)
    prompts = json.loads((HERE / "routing_prompts.json").read_text())
    results = []
    with tempfile.TemporaryDirectory() as scratch:
        for item in prompts:
            for rep in range(1, args.reps + 1):
                workspace = Path(scratch) / f"{item['id']}-r{rep}"
                shutil.copytree(HERE.parent / "fixtures" / item["fixture"], workspace)
                if args.project_rule:
                    (workspace / "CLAUDE.md").write_text(args.project_rule.strip() + "\n")
                outcome = await probe(item["prompt"], workspace, args.plugin.resolve(), args.model, args.max_turns, user_setup,
                                      project_rule=bool(args.project_rule))
                results.append({"id": item["id"], "rep": rep, "expected": item["expected"], **outcome})
                print(f"{item['id']:22} r{rep} expected={item['expected']!s:5} triggered={outcome['triggered']!s:5} {outcome['first_tools']}")
    should = [r for r in results if r["expected"]]
    should_not = [r for r in results if not r["expected"]]
    summary = {
        "recall": f"{sum(r['triggered'] for r in should)}/{len(should)}",
        "false_triggers": f"{sum(r['triggered'] for r in should_not)}/{len(should_not)}",
        "cost_usd": round(sum(r["cost_usd"] for r in results), 3),
        "skills_listed": sorted({r["skills_listed"] for r in results if r["skills_listed"] is not None}),
        "user_setup": args.user_setup,
        "project_rule": args.project_rule,
    }
    (args.out / "routing.json").write_text(json.dumps({"summary": summary, "results": results}, indent=1, ensure_ascii=False))
    print(json.dumps(summary))


if __name__ == "__main__":
    asyncio.run(main())
