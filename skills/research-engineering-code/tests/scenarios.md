# Evaluation cases

The evaluation is interactive. Each episode is an agent session plus a simulated user, run on a fresh fixture copy, then checked and judged. Exact prompts, splits and checks are in [eval-plan.json](eval-plan.json); prompts, briefs and turn limits in [interactive/cases.json](interactive/cases.json); fixture commands and hidden tests in [harness.json](harness.json).

These are evaluation cases, not evidence. What has been observed is recorded in [validation.md](validation.md).

## How an episode works

1. [run_round.py](interactive/run_round.py) builds a clean plugin copy for the variant (never including `tests/`) and a fresh workspace from the case's fixture.
2. [run_interactive.py](interactive/run_interactive.py) starts an Agent SDK session with no user, project or local settings, so only Claude Code's built-in skills and the plugin under test load. A second model plays the user from a private brief:
   - It sees only what a user would see.
   - It answers `AskUserQuestion` live, and approves, corrects or ends at each turn end.
   - It reveals at most two brief items per reply, and only to answer a question or to correct a direct contradiction.
   - Writes outside the workspace, network access and package installs are refused.
3. [check_run.py](check_run.py) compares the workspace with the fixture: files, tests, scope (new public names and flags), the project's suite, the hidden tests, lint, and mutation. It caps CPU per process and kills and reports any leftover process.
4. [judge.py](interactive/judge.py) reads the brief, the conversation (with every trace of the skill removed) and the diff. It grades readability, scope, test quality and whether a plan came first, and audits every simulated-user reply.
5. [summarize.py](interactive/summarize.py) tabulates a round per episode and per case and variant.

Evidence goes to a durable directory outside the repository, given with `--out`. A previous round lost its raw transcripts to a cleared temporary folder.

## Fixtures

| Fixture | Stack | Planted problem |
| --- | --- | --- |
| [tinylab](fixtures/tinylab) | Python and NumPy, pytest | Batch shuffling uses NumPy's global state, so a seed does not pin a run. |
| [decaysim](fixtures/decaysim) | C solver, Python analysis, Bash pipeline; `make test` with plain C asserts and `unittest` | `run.sh` parses `--dt` but passes a hard-coded `0.1` to the solver. |

Report results per stack. These two fixtures say nothing about R, Julia, Rust, MATLAB or GPU code.

## Interactive cases

Each case targets one rule of the skill. The brief holds what the prompt leaves out; the hidden tests check only what the brief defines.

| Case | Fixture | Rule under test | What good behaviour looks like |
| --- | --- | --- | --- |
| [c09i config runner](interactive/briefs/c09i-config-runner.md) | tinylab | Plan first, settle open interfaces, thin end-to-end path, scope | Shows a plan, asks about or confirms the interface before building, builds only the brief, reports the seeding bug without changing `train`. |
| [m01i midpoint](interactive/briefs/m01i-midpoint.md) | decaysim | The same across C, Bash and Python; unchanged numbers | Settles method name, selection and summary field; shows Euler's numbers are unchanged; reports `--dt` without fixing it. |
| [c03i seed bug](interactive/briefs/c03i-seed-bug.md) | tinylab | Local fix: short plan, reproducing test first | Three-line plan, a failing test before the fix, no global reseeding, no extras. |
| [c10i empty accuracy](interactive/briefs/c10i-empty-accuracy.md) | tinylab | Proportion | One-to-three-line plan, one or two tests, no new public names, no needless questions. |
| [c11i away](interactive/briefs/c11i-away.md) | tinylab | Nobody can answer | States assumptions and proceeds instead of waiting, lists them in the report, reports rather than fixes the seeding bug. |
| [c07i throwaway plot](interactive/briefs/c07i-throwaway-plot.md) | tinylab | Staying out of the way | Ideally the skill does not load; either way the figure, no tests, no package changes. |

Before any agent run, each case's hidden tests were checked against three workspaces: a correct reference (passes), the untouched fixture (fails), and a loophole (fails on the intended test). See validation.md.

## Routing

[routing_prompts.json](interactive/routing_prompts.json) holds 12 requests: 8 that should trigger the skill (including Chinese ones) and 4 that should not. [routing.py](interactive/routing.py) runs each in a short, read-only session with only the plugin loaded, and counts a Skill call for the target as a trigger.

## Variants

| Variant | Content | Scheduled for |
| --- | --- | --- |
| `baseline` | No plugin | every case |
| `current` | This directory without `tests/` (0.3.0) | every case |
| `previous-0.2.0` | [variants/previous-0.2.0](variants/previous-0.2.0) | c09i and m01i |
| `previous-0.1.0`, `literal-atomic` | [variants/](variants) | not scheduled |

## Measures

Deterministic, from `metrics.json` and `check.json`:

- **Plan:** characters of agent text before the first edit, and whether turn 1 already edited files.
- **User effort:** questions asked, corrections the user had to make, replies until done.
- **Scope:** new public names and new command-line flags.
- **Tests:** tests added, and the mutation score among mutants the hidden tests can see.
- **Outcome:** hidden tests, including the end-to-end ones.
- **Integrity:** simulated-user replies over the two-item limit, leftover processes, cost.

From the judge: readability (1–5), things built beyond the request, test proportion and independence, plan before building, unrequested changes reported, and a per-reply fidelity audit of the simulated user. An episode with a flagged reply is reported separately.

## Legacy single-turn cases

The single-turn cases c01–c10, h01–h04, m01 and m02 remain in harness.json so check_run.py can still grade them, and their results are in validation.md. They are superseded by the interactive cases. The held-out set is still to be rebuilt in interactive form before any revision is evaluated on it.
