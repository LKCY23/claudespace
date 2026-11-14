"""Run one interactive evaluation episode: an isolated agent session and a simulated user.

The executor is a Claude Code session started through the Agent SDK with no user,
project or local settings, so it sees only Claude Code's built-in skills plus, for
the skill variant, the target plugin. The simulated user is a separate model call
that sees only what a user would see (the agent's messages and questions) and a
private brief for the case. It answers questions, approves or redirects plans, and
ends the episode when the work is done or the turn budget runs out.

Everything is written to --out: transcript.jsonl (every SDK message), simulator.jsonl
(every simulated-user decision), permissions.jsonl, conversation.md (a readable view)
and metrics.json. Run with an interpreter that has claude-agent-sdk:

    uv run --no-project --with claude-agent-sdk python run_interactive.py \
        --case c09i-config-runner --variant current --workspace /path/to/ws \
        --out /path/to/evidence --plugin /path/to/skill
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

HERE = Path(__file__).resolve().parent
WRITE_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}
DENIED_TOOLS = {"WebFetch", "WebSearch"}
DENIED_BASH = re.compile(r"\b(curl|wget|sudo|ssh|scp)\b|\bgit\s+push\b|\b(pip|uv\s+pip|conda|brew|npm)\s+install\b")
REDACT = re.compile(r"research[-_ ]engineering[-_ ]code[\w:-]*", re.IGNORECASE)

SIMULATOR_SYSTEM = """You are role-playing a user who asked a coding agent for help with their research code. \
You only see what the user would see: the agent's messages and questions. You have a private brief describing \
what you actually want; the agent has not seen it.

Rules:
- Stay in character as described in the brief. Write as that person would type: short, plain, 1-3 sentences.
- Answer every question the agent asked, briefly, only from the brief. If the brief does not cover a question, \
answer "Your call." or similar.
- Beyond those answers, correct at most two things in the agent's plan or result that contradict the brief, the \
most important ones, in your own words. A real user corrects what they see, a bit at a time.
- Never volunteer anything the agent neither asked about nor contradicted, and never restate the brief.
- The agent may state a design and assumptions and keep working without asking. That is fine. Correct only what \
contradicts the brief, under the rule above.
- Before ending, go through the brief item by item against what the agent delivered and reported. End the \
conversation only if nothing contradicts it.
- Never write code, never mention tests that will be run, never reveal that you have a brief.
- Never claim you said something earlier unless it appears in the conversation; state the wish now instead.

Reply with a single JSON object and nothing else:
{"type": "answer" | "approve" | "redirect" | "end" | "unknown",
 "reply": "<your message to the agent; empty when type is end>",
 "brief_items": ["<ids of brief items your reply draws on>"]}

For a question event the agent receives only "answers": {"<exact question text>": "<option label or free text>"}. \
Put everything you want to say into those answers; "reply" is not delivered."""


def to_jsonable(message) -> dict:
    if dataclasses.is_dataclass(message):
        data = dataclasses.asdict(message)
    else:
        data = {"repr": repr(message)}
    data["_type"] = type(message).__name__
    return data


class Episode:
    def __init__(self, args, case: dict, brief: str):
        self.args, self.case, self.brief = args, case, brief
        self.workspace = Path(args.workspace).resolve()
        self.out = Path(args.out).resolve()
        self.out.mkdir(parents=True, exist_ok=False)
        self.transcript = (self.out / "transcript.jsonl").open("w")
        self.sim_log = (self.out / "simulator.jsonl").open("w")
        self.perm_log = (self.out / "permissions.jsonl").open("w")
        self.visible: list[str] = []  # what the simulated user has seen, in order
        self.pending_agent_text: list[str] = []
        self.tool_sequence: list[dict] = []
        self.simulator_cost = 0.0
        self.results: list[dict] = []
        self.turn_changes: list[dict] = []
        self.init: dict = {}

    def snapshot_turn(self, user_turn: int):
        """Record which files differ from the committed fixture at the end of a turn."""
        import subprocess

        done = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=self.workspace,
                              capture_output=True, text=True, check=False)
        changed = sorted(line[3:] for line in done.stdout.splitlines() if line.strip())
        self.turn_changes.append({"turn": user_turn, "changed": changed})
        with (self.out / "turn_changes.jsonl").open("a") as handle:
            handle.write(json.dumps(self.turn_changes[-1]) + "\n")

    # ------------------------------------------------------------- simulated user

    async def simulate(self, event: str, payload: str) -> dict:
        history = "\n\n".join(self.visible)
        prompt = (
            f"## Your private brief\n\n{self.brief}\n\n## Conversation so far\n\n{history}\n\n"
            f"## Event: {event}\n\n{payload}\n\nRespond with the JSON object only."
        )
        options = ClaudeAgentOptions(
            model=self.args.simulator_model, system_prompt=SIMULATOR_SYSTEM, tools=[], setting_sources=[],
            max_turns=1, cli_path=shutil.which("claude"), strict_mcp_config=True,
        )
        decision, raw = None, ""
        for _ in range(2):
            raw = ""
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    raw += "".join(b.text for b in message.content if isinstance(b, TextBlock))
                if isinstance(message, ResultMessage):
                    self.simulator_cost += message.total_cost_usd or 0.0
            try:
                decision = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
                break
            except json.JSONDecodeError:
                prompt += "\n\nYour last reply was not valid JSON. Reply with the JSON object only."
        if decision is None:
            decision = {"type": "unknown", "reply": "Your call.", "brief_items": [], "parse_error": raw[:500]}
        self.sim_log.write(json.dumps({"event": event, "payload": payload, "decision": decision}) + "\n")
        self.sim_log.flush()
        return decision

    # ------------------------------------------------------------- permissions

    def inside(self, path: str) -> bool:
        resolved = Path(path).expanduser().resolve()
        if resolved == self.workspace or self.workspace in resolved.parents:
            return True
        temp_roots = {Path(tempfile.gettempdir()).resolve(), Path("/private/tmp"), Path("/tmp").resolve()}
        eval_root = self.workspace.parents[2] if len(self.workspace.parents) > 2 else self.workspace
        in_temp = any(root in resolved.parents for root in temp_roots)
        return in_temp and eval_root not in resolved.parents and resolved != eval_root

    async def can_use_tool(self, tool_name, tool_input, context):
        verdict, note = "allow", ""
        if tool_name == "AskUserQuestion":
            questions = tool_input.get("questions", [])
            payload = REDACT.sub("[redacted]", json.dumps(questions, ensure_ascii=False, indent=1))
            self.flush_agent_text()
            decision = await self.simulate("question", payload)
            answers = decision.get("answers") or {}
            final = {q["question"]: answers.get(q["question"]) or decision.get("reply") or "Your call." for q in questions}
            self.visible.append("AGENT ASKED:\n" + payload)
            self.visible.append("USER ANSWERED: " + json.dumps(final, ensure_ascii=False))
            self.log_perm(tool_name, tool_input, "allow", "answered by simulated user")
            return PermissionResultAllow(updated_input={**tool_input, "answers": final})
        if tool_name in DENIED_TOOLS:
            verdict, note = "deny", "network tools are disabled in this evaluation"
        elif tool_name in WRITE_TOOLS:
            path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
            if not self.inside(path):
                verdict, note = "deny", "writes are limited to the project directory and temporary files"
        elif tool_name == "Bash" and DENIED_BASH.search(tool_input.get("command", "")):
            verdict, note = "deny", "network access and package installation are disabled in this evaluation"
        self.log_perm(tool_name, tool_input, verdict, note)
        return PermissionResultAllow() if verdict == "allow" else PermissionResultDeny(message=note)

    def log_perm(self, tool, tool_input, verdict, note):
        self.perm_log.write(json.dumps({"tool": tool, "input": tool_input, "verdict": verdict, "note": note}, default=str) + "\n")
        self.perm_log.flush()

    # ------------------------------------------------------------- episode

    def flush_agent_text(self):
        if self.pending_agent_text:
            self.visible.append("AGENT: " + REDACT.sub("[redacted]", "\n\n".join(self.pending_agent_text)))
            self.pending_agent_text = []

    def record(self, message, user_turn: int):
        self.transcript.write(json.dumps({"user_turn": user_turn, **to_jsonable(message)}, default=str) + "\n")
        self.transcript.flush()
        if isinstance(message, SystemMessage) and message.subtype == "init":
            self.init = message.data
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock) and block.text.strip():
                    self.pending_agent_text.append(block.text.strip())
                    self.tool_sequence.append({"turn": user_turn, "kind": "text", "chars": len(block.text)})
                elif isinstance(block, ToolUseBlock):
                    detail = block.input.get("command") or block.input.get("file_path") or block.input.get("skill") or ""
                    self.tool_sequence.append({"turn": user_turn, "kind": "tool", "name": block.name, "detail": str(detail)})
        if isinstance(message, ResultMessage):
            self.results.append({"turn": user_turn, "cost": message.total_cost_usd, "num_turns": message.num_turns,
                                 "is_error": message.is_error, "subtype": message.subtype, "result": message.result})

    async def run(self):
        plugins = [{"type": "local", "path": str(Path(self.args.plugin).resolve())}] if self.args.plugin else []
        options = ClaudeAgentOptions(
            cwd=str(self.workspace), model=self.args.model, setting_sources=[], plugins=plugins,
            cli_path=shutil.which("claude"), strict_mcp_config=True, can_use_tool=self.can_use_tool,
            permission_mode="default", max_budget_usd=self.args.budget,
        )
        prompt = self.case["prompt"]
        self.visible.append("USER: " + prompt)
        user_turn, end_reason = 0, "turn budget exhausted"
        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)
            while True:
                async for message in client.receive_response():
                    self.record(message, user_turn)
                self.flush_agent_text()
                self.snapshot_turn(user_turn)
                if user_turn >= self.case.get("max_user_turns", 4):
                    break
                decision = await self.simulate("turn_end", "The agent has finished its turn and is waiting for you.")
                if decision.get("type") == "end" or not decision.get("reply"):
                    end_reason = "simulated user ended the conversation"
                    break
                user_turn += 1
                self.visible.append("USER: " + decision["reply"])
                await client.query(decision["reply"])
        return end_reason


# ----------------------------------------------------------------- reporting


BASH_WRITE = re.compile(r"(?<![<>&0-9])>{1,2}\s*(?!&|/dev/null)[\w./$\"'-]|\btee\b|\bsed\s+-i|\.write_text\(|\.write\(|open\([^)]*['\"][wa]['\"]|\bmv\b|\bcp\b|\brm\b")
EXECUTES = re.compile(r"\bpytest\b|-m\s+tinylab|\bmake\b|run\.sh|python[\w./]*\s+(?!-\s*<<)[\w./-]+\.py")


def is_write(step: dict) -> bool:
    """A file-writing tool call, including shell commands that write files."""
    if step.get("name") in WRITE_TOOLS:
        return True
    return step.get("name") == "Bash" and bool(BASH_WRITE.search(step.get("detail", "")))


def is_run(step: dict) -> bool:
    """A shell command that executes project code or its tests."""
    return step.get("name") == "Bash" and bool(EXECUTES.search(step.get("detail", ""))) and not is_write(step)


def metrics(ep: Episode, end_reason: str, elapsed: float) -> dict:
    decisions = [json.loads(line) for line in (ep.out / "simulator.jsonl").read_text().splitlines()]
    seq = ep.tool_sequence
    first_edit = next((i for i, s in enumerate(seq) if is_write(s)), None)
    first_run = next((i for i, s in enumerate(seq) if is_run(s)), None)
    text_before_edit = sum(s["chars"] for s in seq[: first_edit if first_edit is not None else len(seq)] if s["kind"] == "text")
    writes_before_run = sum(1 for s in seq[: first_run if first_run is not None else len(seq)] if is_write(s))
    questions = [d for d in decisions if d["event"] == "question"]
    turn_ends = [d for d in decisions if d["event"] == "turn_end"]
    def items(ds):
        return sorted({i for d in ds for i in d["decision"].get("brief_items", [])})

    return {
        "end_reason": end_reason,
        "user_turns": max((s["turn"] for s in seq), default=0),
        "skills_listed": len(ep.init.get("skills", [])),
        "plugins": [p.get("name") for p in ep.init.get("plugins", [])],
        "target_loaded_by_skill_tool": any(s.get("name") == "Skill" for s in seq),
        "ask_user_question_calls": len(questions),
        "turn_end_decisions": [d["decision"].get("type") for d in turn_ends],
        "brief_items_answered_on_question": items(questions + [d for d in turn_ends if d["decision"].get("type") in {"answer", "approve"}]),
        "brief_items_corrected_by_user": items([d for d in turn_ends if d["decision"].get("type") == "redirect"]),
        "simulator_replies_over_two_items": sum(1 for d in decisions if len(d["decision"].get("brief_items", [])) > 2),  # informational; the judge decides
        # The end-of-turn file snapshot is authoritative; the tool-call heuristic is the fallback.
        "first_turn_had_edits": (bool(ep.turn_changes[0]["changed"]) if ep.turn_changes
                                 else any(is_write(s) for s in seq if s["turn"] == 0)),
        "files_changed_per_turn": [len(t["changed"]) for t in ep.turn_changes],
        "agent_text_chars_before_first_edit": text_before_edit,
        "writes_before_first_run": writes_before_run,
        "tool_calls": sum(1 for s in seq if s["kind"] == "tool"),
        "permission_denials": sum(1 for line in (ep.out / "permissions.jsonl").read_text().splitlines() if '"deny"' in line),
        "executor_cost_usd": round(sum(r["cost"] or 0 for r in ep.results), 4),
        "simulator_cost_usd": round(ep.simulator_cost, 4),
        "elapsed_seconds": round(elapsed),
    }


def conversation_md(ep: Episode) -> str:
    lines = [f"# {ep.case['id']} ({ep.args.variant})", ""]
    sims = [json.loads(line) for line in (ep.out / "simulator.jsonl").read_text().splitlines()]
    turn = -1
    for entry in (json.loads(line) for line in (ep.out / "transcript.jsonl").read_text().splitlines()):
        if entry["user_turn"] != turn:
            turn = entry["user_turn"]
            if turn == 0:
                lines += ["## User", "", ep.case["prompt"], ""]
            else:
                reply = [d for d in sims if d["event"] == "turn_end"][turn - 1]["decision"]
                lines += [f"## User ({reply.get('type')})", "", reply.get("reply", ""), ""]
        if entry["_type"] == "AssistantMessage":
            for block in entry["content"]:
                if "text" in block and block.get("text", "").strip():
                    lines += ["**Agent:** " + block["text"].strip(), ""]
                elif "name" in block:
                    detail = block["input"].get("command") or block["input"].get("file_path") or block["input"].get("skill") or ""
                    if block["name"] == "AskUserQuestion":
                        detail = json.dumps(block["input"].get("questions"), ensure_ascii=False)
                    lines.append(f"- `{block['name']}` {str(detail)[:200]}")
    end = [d for d in sims if d["event"] == "turn_end"]
    if end and end[-1]["decision"].get("type") == "end":
        lines += ["", "## User (end)", ""]
    for d in (d for d in sims if d["event"] == "question"):
        lines += ["", "### Question answered by the simulated user", "", d["payload"][:800], "", "→ " + json.dumps(d["decision"].get("answers"), ensure_ascii=False)]
    return "\n".join(lines) + "\n"


def recompute(out: Path) -> dict:
    """Rebuild metrics.json for a finished episode from its saved transcript."""
    seq = []
    for entry in (json.loads(line) for line in (out / "transcript.jsonl").read_text().splitlines()):
        if entry["_type"] != "AssistantMessage":
            continue
        for block in entry["content"]:
            if block.get("text", "").strip():
                seq.append({"turn": entry["user_turn"], "kind": "text", "chars": len(block["text"])})
            elif "name" in block:
                detail = block["input"].get("command") or block["input"].get("file_path") or block["input"].get("skill") or ""
                seq.append({"turn": entry["user_turn"], "kind": "tool", "name": block["name"], "detail": str(detail)})
    ep = argparse.Namespace(out=out, tool_sequence=seq, results=[], simulator_cost=0.0,
                            init=json.loads((out / "init.json").read_text()), turn_changes=[])
    if (out / "turn_changes.jsonl").exists():
        ep.turn_changes = [json.loads(line) for line in (out / "turn_changes.jsonl").read_text().splitlines()]
    old = json.loads((out / "metrics.json").read_text())
    record = metrics(ep, old["end_reason"], old["elapsed_seconds"])
    record["executor_cost_usd"], record["simulator_cost_usd"] = old["executor_cost_usd"], old["simulator_cost_usd"]
    (out / "metrics.json").write_text(json.dumps(record, indent=1))
    return record


async def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", required=True)
    parser.add_argument("--variant", required=True, help="label only; the plugin decides what loads")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--plugin", help="target plugin directory; omit for the baseline")
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--simulator-model", default="sonnet")
    parser.add_argument("--budget", type=float, default=4.0, help="executor budget in USD")
    parser.add_argument("--timeout", type=int, default=1500)
    args = parser.parse_args()

    cases = json.loads((HERE / "cases.json").read_text())
    case = {"id": args.case, **cases[args.case]}
    brief = (HERE / case["brief"]).read_text()
    episode = Episode(args, case, brief)
    started = time.monotonic()
    try:
        end_reason = await asyncio.wait_for(episode.run(), timeout=args.timeout)
    except TimeoutError:
        end_reason = "timeout"
    finally:
        for handle in (episode.transcript, episode.sim_log, episode.perm_log):
            handle.close()
    record = metrics(episode, end_reason, time.monotonic() - started)
    (episode.out / "init.json").write_text(json.dumps(episode.init, indent=1, default=str))
    (episode.out / "metrics.json").write_text(json.dumps(record, indent=1))
    (episode.out / "conversation.md").write_text(conversation_md(episode))
    print(json.dumps(record, indent=1))


if __name__ == "__main__":
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    import sys

    if len(sys.argv) == 3 and sys.argv[1] == "--recompute":
        print(json.dumps(recompute(Path(sys.argv[2]).resolve()), indent=1))
    else:
        asyncio.run(main())
