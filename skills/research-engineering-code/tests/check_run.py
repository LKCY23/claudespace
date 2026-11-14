"""Deterministic checks for one evaluation run of research-engineering-code.

Compares a finished workspace with the untouched fixture of its case and prints
one JSON record. It measures; it does not grade. Fixtures, suite commands and
hidden acceptance tests are declared in harness.json next to this file. Run it
with an interpreter that has pytest and numpy (and ruff, for the lint check):

    uv run --no-project --with pytest --with numpy --with ruff python check_run.py \
        --case c01-label-smoothing --workspace /path/to/run/tinylab
"""

from __future__ import annotations

import argparse
import ast
import difflib
import json
import os
import re
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from fnmatch import fnmatch
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Everything this checker starts works inside TMPROOT (its scratch directories and TMPDIR)
# or the workspace. A process still running from there after its command ended is a leftover.
TMPROOT = Path(tempfile.mkdtemp(prefix="check-run-")).resolve()
tempfile.tempdir = str(TMPROOT)  # this process's own scratch directories live there too
SWEEP_ROOTS: list[Path] = [TMPROOT]
CPU_SECONDS = 300  # per process; set by --cpu-limit
LEFTOVERS: list[dict] = []
STARTED = time.monotonic()
IGNORED_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", "build", "node_modules"}
IGNORED_FILES = {".DS_Store"}
IGNORED_SUFFIXES = {".pyc", ".o"}
STARTUP_HOOKS = {"sitecustomize.py", "usercustomize.py"}
SKIP_MARKER = re.compile(
    r"pytest\.mark\.(?:skip|skipif|xfail)\b|pytest\.(?:skip|xfail|importorskip)\(|unittest\.skip|skipTest\(|expectedFailure|@skip\b"
)
PYTEST_COUNT = re.compile(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed|deselected)\b")
UNITTEST_COUNT = re.compile(r"\b(failures|errors|skipped|expected failures)=(\d+)")
SWAPS = {
    ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Div, ast.Div: ast.Mult,
    ast.Lt: ast.GtE, ast.GtE: ast.Lt, ast.Gt: ast.LtE, ast.LtE: ast.Gt,
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
}


# ---------------------------------------------------------------- files


def snapshot(root: Path) -> dict[str, bytes]:
    """Every file under root except caches, virtualenvs and build output, keyed by relative path."""
    files = {}
    for directory, subdirs, names in os.walk(root):
        subdirs[:] = sorted(d for d in subdirs if d not in IGNORED_DIRS and not d.endswith(".egg-info"))
        for name in sorted(names):
            if name in IGNORED_FILES or Path(name).suffix in IGNORED_SUFFIXES:
                continue
            path = Path(directory, name)
            files[path.relative_to(root).as_posix()] = path.read_bytes()
    return files


def category(relative: str, patterns: dict[str, list[str]]) -> str:
    for name in ("test_config", "test", "source"):
        if any(fnmatch(relative, pattern) for pattern in patterns.get(name, [])):
            return name
    return "other"


def file_changes(before: dict, after: dict, patterns: dict) -> dict:
    added = sorted(set(after) - set(before))
    deleted = sorted(set(before) - set(after))
    modified = sorted(r for r in set(before) & set(after) if before[r] != after[r])

    def grouped(paths):
        groups: dict[str, list[str]] = {}
        for relative in paths:
            groups.setdefault(category(relative, patterns), []).append(relative)
        return groups

    touched = added + modified + deleted
    return {
        "added": grouped(added),
        "modified": grouped(modified),
        "deleted": grouped(deleted),
        "test_config_changed": [r for r in touched if category(r, patterns) == "test_config"],
        "startup_hooks_added": [r for r in added + modified if Path(r).name in STARTUP_HOOKS or r.endswith(".pth")],
    }


# ---------------------------------------------------------------- tests


def test_names(relative: str, data: bytes, pattern: str | None) -> set[str]:
    text = data.decode(errors="replace")
    if relative.endswith(".py"):
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return {"<unparseable>"}
        return {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test")}
    return set(re.findall(pattern, text, re.MULTILINE)) if pattern else set()


def skip_markers(data: bytes | None) -> int:
    return len(SKIP_MARKER.findall(data.decode(errors="replace"))) if data else 0


def private_accesses(data: bytes) -> list[str]:
    """Underscore names a Python test imports or reads from another module or object."""
    try:
        tree = ast.parse(data.decode(errors="replace"))
    except SyntaxError:
        return []
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            hits += [f"import {a.name}" for a in node.names if a.name.startswith("_") and not a.name.startswith("__")]
        elif (
            isinstance(node, ast.Attribute)
            and node.attr.startswith("_")
            and not node.attr.startswith("__")
            and not (isinstance(node.value, ast.Name) and node.value.id in {"self", "cls"})
        ):
            hits.append(f"attribute {node.attr}")
    return sorted(set(hits))


def test_record(before: dict, after: dict, fixture: dict) -> dict:
    patterns, name_pattern = fixture["files"], fixture.get("test_name_pattern")
    old = {r: test_names(r, d, name_pattern) for r, d in before.items() if category(r, patterns) == "test"}
    new = {r: test_names(r, d, name_pattern) for r, d in after.items() if category(r, patterns) == "test"}
    changed = [r for r in new if r not in before or before[r] != after[r]]
    entry = re.compile(fixture["entry_point_pattern"]) if fixture.get("entry_point_pattern") else None
    markers_added = {}
    for relative in set(before) | set(after):
        if category(relative, patterns) in {"test", "test_config"}:
            gained = skip_markers(after.get(relative)) - skip_markers(before.get(relative))
            if gained > 0:
                markers_added[relative] = gained
    return {
        "added": sorted(f"{r}::{n}" for r, names in new.items() for n in names - old.get(r, set())),
        "removed": sorted(f"{r}::{n}" for r, names in old.items() for n in names - new.get(r, set())),
        "existing_files_edited": sorted(r for r in old if r in after and before[r] != after[r]),
        "skip_markers_added": dict(sorted(markers_added.items())),
        "private_access": {r: hits for r in new if r.endswith(".py") and (hits := private_accesses(after[r]))},
        "changed_files_reaching_entry_point": sorted(r for r in changed if entry and entry.search(after[r].decode(errors="replace"))),
    }


# ---------------------------------------------------------------- surface

FLAG = re.compile(rb"""(?<![\w-])(--[a-z][a-z0-9-]+)""")


def public_names(data: bytes) -> set[str]:
    """Module-level functions, classes and constants a caller could import."""
    try:
        tree = ast.parse(data.decode(errors="replace"))
    except SyntaxError:
        return set()
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return {n for n in names if not n.startswith("_")}


def surface_record(before: dict, after: dict, patterns: dict) -> dict:
    """What a caller can now reach that it could not before: new public names and new command-line flags.

    A scope measure: every item here should trace back to the request or the agreed plan.
    """
    names, flags = [], []
    for relative, data in after.items():
        if category(relative, patterns) != "source" or before.get(relative) == data:
            continue
        old = before.get(relative, b"")
        if relative.endswith(".py"):
            names += [f"{relative}::{n}" for n in sorted(public_names(data) - public_names(old))]
        flags += [f"{relative}::{f.decode()}" for f in sorted(set(FLAG.findall(data)) - set(FLAG.findall(old)))]
    return {"public_names_added": names, "flags_added": flags}


# ---------------------------------------------------------------- running


def expand(items, workspace: Path):
    return [str(i).replace("{python}", sys.executable).replace("{workspace}", str(workspace)) for i in items]


def limit_cpu() -> None:
    """Runs in each child before it starts: the OS stops it after CPU_SECONDS of CPU time.

    The limit is inherited, so a training run started by a hidden test is capped too.
    """
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS + 10))


def under_roots(path: str) -> bool:
    real = os.path.realpath(path)
    return any(real == str(root) or real.startswith(str(root) + os.sep) for root in SWEEP_ROOTS)


def elapsed_seconds(etime: str) -> int:
    """Parse ps etime, [[dd-]hh:]mm:ss, into seconds."""
    days, _, rest = etime.rpartition("-")
    parts = [int(x) for x in rest.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    return int(days or 0) * 86400 + parts[0] * 3600 + parts[1] * 60 + parts[2]


def sweep_leftovers() -> list[dict]:
    """Kill processes this checker run left behind, and say which ones they were.

    A leftover is a process that started after this checker did, is not one of its
    ancestors, and has a command line or working directory inside the sweep roots.
    The age test matters: without it, a terminal or editor the user already had open
    in a workspace, or the shell that launched this checker, would match too.
    """
    listing = subprocess.run(["ps", "-Aww", "-o", "pid=,ppid=,etime=,command="], capture_output=True, text=True, check=False).stdout
    table = {}
    for line in listing.splitlines():
        fields = line.split(None, 3)
        if len(fields) == 4 and fields[0].isdigit() and fields[1].isdigit():
            table[int(fields[0])] = (int(fields[1]), fields[2], fields[3])
    protected, pid = set(), os.getpid()
    while pid in table and pid not in protected:  # this process and every ancestor
        protected.add(pid)
        pid = table[pid][0]
    own_age = time.monotonic() - STARTED
    # ps truncates etime to whole seconds, so anything this run started reads as no older than the run.
    young = {pid for pid, (_, etime, _) in table.items() if elapsed_seconds(etime) <= own_age}
    suspects = {pid for pid in young if any(str(root) in table[pid][2] for root in SWEEP_ROOTS)}
    cwd_listing = subprocess.run(["lsof", "-a", "-d", "cwd", "-u", str(os.getuid()), "-Fpn"],
                                 capture_output=True, text=True, check=False).stdout
    pid = None
    for line in cwd_listing.splitlines():
        if line.startswith("p") and line[1:].isdigit():
            pid = int(line[1:])
        elif line.startswith("n") and pid in young and under_roots(line[1:]):
            suspects.add(pid)
    found = []
    for pid in sorted(suspects - protected):
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            continue
        found.append({"pid": pid, "command": table[pid][2][:200]})
    LEFTOVERS.extend(found)
    return found


def stop_group(process: subprocess.Popen) -> None:
    """Kill the process group started for one command, ignoring a group that is already gone."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    if process.poll() is None:
        process.wait()


def run(command: list[str], cwd: Path, env_extra: dict, timeout: int) -> dict:
    """Run a command and classify it: pass, fail (tests ran and failed), error (could not run tests) or timeout."""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", TMPDIR=str(TMPROOT), **env_extra)
    # A new session puts the command and everything it starts in one process group, so a
    # timeout can stop all of it. Killing only the direct child once left mutated training
    # loops that the hidden tests had started running for hours.
    # Output goes to files, not pipes, so a leftover background child cannot hold the
    # command open: it is judged by its own exit.
    with tempfile.TemporaryFile("w+") as out, tempfile.TemporaryFile("w+") as err:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=out, stderr=err, text=True,
                                   start_new_session=True, preexec_fn=limit_cpu)  # noqa: PLW1509 - no threads here
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            stop_group(process)
            sweep_leftovers()
            return {"outcome": "timeout", "exit_code": None}
        finally:
            stop_group(process)  # also stops anything left behind after a normal exit
        sweep_leftovers()
        out.seek(0)
        err.seek(0)
        done = subprocess.CompletedProcess(command, process.returncode, out.read(), err.read())
    output = done.stdout + "\n" + done.stderr
    is_pytest = "pytest" in command
    if done.returncode == 0:
        outcome = "pass"
    elif is_pytest:
        outcome = "fail" if done.returncode == 1 else "error"
    else:
        outcome = "fail"
    counts: dict[str, int] = {}
    for number, word in PYTEST_COUNT.findall(output):
        counts[word.rstrip("s") if word.startswith("error") else word] = int(number)
    if ran := re.findall(r"^Ran (\d+) tests?", output, re.MULTILINE):
        counts["unittest_ran"] = sum(int(n) for n in ran)
        for word, number in UNITTEST_COUNT.findall(output):
            counts[f"unittest_{word.replace(' ', '_')}"] = counts.get(f"unittest_{word.replace(' ', '_')}", 0) + int(number)
    tail = [line for line in output.splitlines() if line.strip()][-3:]
    return {"outcome": outcome, "exit_code": done.returncode, "counts": counts, "tail": tail}


def run_suite(workspace: Path, fixture: dict, timeout: int = 300) -> dict:
    return run(expand(fixture["suite"], workspace), workspace, dict(zip(fixture["env"], expand(fixture["env"].values(), workspace))), timeout)


def run_acceptance(workspace: Path, acceptance: Path, fixture: dict, timeout: int = 600) -> dict:
    """Run the hidden tests from a scratch directory, so no workspace config or conftest can reach them."""
    env = dict(zip(fixture["env"], expand(fixture["env"].values(), workspace)), WORKSPACE=str(workspace))
    with tempfile.TemporaryDirectory() as scratch:
        scratch_path = Path(scratch)
        shutil.copy(acceptance, scratch_path / acceptance.name)
        (scratch_path / "pytest.ini").write_text("[pytest]\n")
        junit = scratch_path / "junit.xml"
        command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-c", str(scratch_path / "pytest.ini"),
                   "--rootdir", scratch, f"--junitxml={junit}", acceptance.name]
        result = run(command, scratch_path, env, timeout)
        failed, passed = [], []
        if junit.exists():
            for case in ET.parse(junit).iter("testcase"):
                bad = case.find("failure") is not None or case.find("error") is not None or case.find("skipped") is not None
                (failed if bad else passed).append(case.get("name"))
    result["failed_tests"] = failed

    def group(keep) -> dict:
        names = [n for n in passed + failed if keep(n)]
        return {"passed": len([n for n in names if n in passed]), "total": len(names)}

    # Categories by test-name prefix. Required tests are everything the request names;
    # protections are checks it does not name but that stop a wrong result passing silently;
    # existing tests cover behaviour the request gives no reason to change.
    result["pipeline"] = group(lambda n: n.startswith("test_pipeline"))
    result["protections"] = group(lambda n: n.startswith("test_protection"))
    result["existing"] = group(lambda n: n.startswith("test_existing"))
    result["required"] = group(lambda n: not n.startswith(("test_protection", "test_existing")))
    return result


def lint(workspace: Path, files: list[str], config: Path | None) -> dict:
    if not files:
        return {"available": True, "files": [], "counts": {}}
    command = [sys.executable, "-m", "ruff", "check", "--output-format", "json", "--no-cache", *files]
    with tempfile.TemporaryDirectory() as scratch:
        if config:
            named = Path(scratch) / "pyproject.toml"  # ruff reads [tool.ruff] only from a file with this name
            shutil.copy(config, named)
            command[4:4] = ["--config", str(named)]
        done = subprocess.run(command, check=False, cwd=workspace, capture_output=True, text=True)
    try:
        findings = json.loads(done.stdout)
    except json.JSONDecodeError:
        return {"available": False, "error": done.stderr.strip()[-200:]}
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding["code"] or "syntax"] = counts.get(finding["code"] or "syntax", 0) + 1
    return {"available": True, "files": files, "counts": dict(sorted(counts.items()))}


# ---------------------------------------------------------------- mutation


def changed_lines(before: bytes | None, after: bytes) -> set[int]:
    new = after.decode(errors="replace").splitlines()
    if before is None:
        return set(range(1, len(new) + 1))
    matcher = difflib.SequenceMatcher(None, before.decode(errors="replace").splitlines(), new, autojunk=False)
    return {line + 1 for tag, _, _, j1, j2 in matcher.get_opcodes() if tag in {"replace", "insert"} for line in range(j1, j2)}


class Mutator(ast.NodeTransformer):
    """Apply exactly one mutation, at the site numbered `target`, counting only sites on `lines`."""

    def __init__(self, lines: set[int], target: int | None = None):
        self.lines, self.target, self.seen = lines, target, 0

    def _hit(self, node) -> bool:
        if getattr(node, "lineno", None) not in self.lines:
            return False
        self.seen += 1
        return self.seen - 1 == self.target

    def visit_BinOp(self, node):
        self.generic_visit(node)
        if type(node.op) in SWAPS and self._hit(node):
            node.op = SWAPS[type(node.op)]()
        return node

    def visit_Compare(self, node):
        self.generic_visit(node)
        if len(node.ops) == 1 and type(node.ops[0]) in SWAPS and self._hit(node):
            node.ops = [SWAPS[type(node.ops[0])]()]
        return node

    def visit_Constant(self, node):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool) and self._hit(node):
            return ast.copy_location(ast.Constant(node.value + 1), node)
        return node


def mutation(workspace: Path, before: dict, after: dict, fixture: dict, acceptance: Path | None, max_mutants: int) -> dict:
    """Mutate changed lines of changed Python sources, one site at a time.

    A mutant counts only if the hidden acceptance tests notice it, which drops
    equivalent mutants and code the request does not care about. Of those, the
    score is the share the run's own suite also catches. Crashes, timeouts and
    collection errors are counted apart, never as catches. When the hidden tests
    cannot filter (no acceptance tests, a collection error, or none passing), the
    score is None and only the unfiltered kill rate is reported, so the two are
    never averaged together.
    """
    patterns = fixture["files"]
    changed = [r for r in after if category(r, patterns) == "source" and before.get(r) != after[r]]
    record = {"not_mutated": sorted(r for r in changed if not r.endswith(".py"))}
    sites = []
    for relative in (r for r in changed if r.endswith(".py")):
        lines = changed_lines(before.get(relative), after[relative])
        counter = Mutator(lines)
        try:
            counter.visit(ast.parse(after[relative].decode()))
        except SyntaxError:
            continue
        sites += [(relative, lines, index) for index in range(counter.seen)]
    record["sites_on_changed_lines"] = len(sites)
    if not sites or max_mutants <= 0:
        return {**record, "mutants": 0, "score": None}
    step = max(1, len(sites) // max_mutants)
    chosen = sites[::step][:max_mutants]
    tally = {"killed": 0, "survived": 0, "invisible_to_acceptance": 0, "acceptance_error": 0, "suite_error": 0}
    survivors = []
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / "work"
        shutil.copytree(workspace, copy, ignore=shutil.ignore_patterns(*IGNORED_DIRS))
        # A mutant is visible if it breaks a hidden test that passed before the mutation, so
        # workspaces that miss some hidden tests are still filtered by the ones they pass.
        clean = run_acceptance(copy, acceptance, fixture) if acceptance is not None else {"outcome": "error"}
        filtered = clean["outcome"] in {"pass", "fail"} and (clean["required"]["passed"] + clean["protections"]["passed"]) > 0
        already_failing = set(clean.get("failed_tests", []))
        for relative, lines, index in chosen:
            original = (copy / relative).read_text()
            tree = Mutator(lines, index).visit(ast.parse(original))
            (copy / relative).write_text(ast.unparse(ast.fix_missing_locations(tree)))
            verdict = "fail"
            if filtered:
                mutated = run_acceptance(copy, acceptance, fixture, timeout=300)
                if mutated["outcome"] not in {"pass", "fail"}:
                    verdict = "error"
                else:
                    verdict = "fail" if set(mutated["failed_tests"]) - already_failing else "pass"
            if verdict == "pass":
                tally["invisible_to_acceptance"] += 1
            elif verdict != "fail":
                tally["acceptance_error"] += 1
            else:
                outcome = run_suite(copy, fixture, timeout=120)["outcome"]
                if outcome == "fail":
                    tally["killed"] += 1
                elif outcome == "pass":
                    tally["survived"] += 1
                    survivors.append(f"{relative}#{index}")
                else:
                    tally["suite_error"] += 1
            (copy / relative).write_text(original)
    relevant = tally["killed"] + tally["survived"]
    rate = round(tally["killed"] / relevant, 3) if relevant else None
    return {
        **record,
        "filtered_by_acceptance": filtered,
        "mutants": len(chosen),
        **tally,
        "score": rate if filtered else None,
        "unfiltered_kill_rate": None if filtered else rate,
        "survivors": survivors,
    }


# ---------------------------------------------------------------- main


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", required=True, help="case id in harness.json")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--harness", type=Path, default=HERE / "harness.json")
    parser.add_argument("--ruff-config", type=Path, help="lint changed Python files with this config")
    parser.add_argument("--max-mutants", type=int, default=20)
    parser.add_argument("--cpu-limit", type=int, default=300, help="CPU seconds allowed to each started process")
    args = parser.parse_args()
    global CPU_SECONDS
    CPU_SECONDS = args.cpu_limit

    harness = json.loads(args.harness.read_text())
    case = harness["cases"][args.case]
    fixture = harness["fixtures"][case["fixture"]]
    workspace = args.workspace.resolve()
    SWEEP_ROOTS.append(workspace)
    acceptance = (args.harness.parent / case["acceptance"]).resolve() if case["acceptance"] else None

    # Snapshot before running anything: suites and pipelines write build output.
    before, after = snapshot(args.harness.parent / fixture["path"]), snapshot(workspace)
    changed_python = sorted(r for r in after if r.endswith(".py") and before.get(r) != after[r])
    # Build output is not part of the deliverable and can be stale (a rebuild inside one
    # second of a source change is skipped by make), so tests start from a clean build.
    if fixture.get("clean"):
        run(expand(fixture["clean"], workspace), workspace, {}, 120)
    record = {
        "case": args.case,
        "fixture": case["fixture"],
        "stack": fixture["stack"],
        "files": file_changes(before, after, fixture["files"]),
        "tests": test_record(before, after, fixture),
        "surface": surface_record(before, after, fixture["files"]),
        "suite": run_suite(workspace, fixture),
        "acceptance": run_acceptance(workspace, acceptance, fixture) if acceptance else None,
        "lint": lint(workspace, changed_python, args.ruff_config),
    }
    record["mutation"] = (
        mutation(workspace, before, after, fixture, acceptance, args.max_mutants)
        if record["suite"]["outcome"] == "pass"
        else {"skipped": "suite is not green"}
    )
    sweep_leftovers()
    # Processes that outlived their command and had to be killed. Empty in a clean run;
    # anything here points at a hanging test or mutant worth a look.
    record["leftover_processes"] = LEFTOVERS
    shutil.rmtree(TMPROOT, ignore_errors=True)
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
