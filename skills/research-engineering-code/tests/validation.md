# Validation

## Registration — 2026-11-14

0.4.2 is registered in the root `catalog.json` as `research-engineering-code` (kind skill, tracked source `skills/research-engineering-code`, manual updates, Codex and Claude Code entries `SKILL.md`). Both validation statuses are left as `not-evaluated`, like the repository's other skills: the evidence below is a small pilot on Claude Code only, and no acceptance level was agreed. It is not listed in `marketplaces.json`, so it is not published to a marketplace.

Checks after registering: `sync_marketplaces.py --write` and `--check` report no change; repository structure tests (131) pass; an isolated candidate build of this resource passes the structural check for both hosts (86 files; native loading and runtime not exercised by that build).

## 0.4.4: project setup step and report hint — 2026-11-14

Change (0.4.4, `SKILL.md` `05bd0e24fbe2766f`; 0.4.3 preserved in [variants/previous-0.4.3](variants/previous-0.4.3)): a "Setting up a project" section that, only when the user asks, appends the routing rule to the project's instruction file (`CLAUDE.md` in Claude Code, `AGENTS.md` in Codex); and a closing line in the report when the project is not set up. The skill never edits an instruction file during an ordinary task.

Checked with [interactive/setup_check.py](interactive/setup_check.py): short Sonnet sessions on the tinylab fixture, isolated setup, a `CLAUDE.md` present at the start loaded as project instructions. Results under `outputs/research-engineering-code-eval/2026-11-14-setup-check-0.4.4*`. Cost $1.12 over all attempts.

| Scenario | Expected | Final text |
| --- | --- | --- |
| No instruction file; user asks for setup | `CLAUDE.md` created with the rule, nothing else changed, added lines shown | pass (1/1) |
| Committed `CLAUDE.md` with other content; user asks for setup | Rule appended once, existing lines kept, collaborators and `CLAUDE.local.md` mentioned | pass (1/1) |
| `CLAUDE.md` already holds the rule; user asks for setup | Nothing changes; says it is already set up | pass (1/1) |
| Not set up; ordinary task with the skill invoked by name | Report ends with the setup line; no instruction file created | pass (1/1) |
| Set up; same task | Report says nothing about setup | pass (2/2) |

- **The hint needed three wordings.** As a condition in the report list ("if neither file mentions this skill…") and as a closing "search the two files" step, the agent printed the hint without looking, in a project that was already set up (2 of 3 such runs, although the rule was in its instructions). As a literal first command (`grep -ls …`) whose answer the report uses, it was right in 3 of 3. This is the same pattern as the design step: an action is carried out, a condition to be judged is not.
- **A first version of this check passed for the wrong reason.** In the "set up" scenario the skill had not loaded at all, so no hint could appear. Every scenario now also requires that the skill loaded.
- When the project is not set up, the hint appears only if the skill loads, which without the rule mostly means the user invoked it by name.
- **One run on the larger new-pipeline task** (`p01-lr-study`, Sonnet, `outputs/research-engineering-code-eval/2026-11-14-probe-0.4.4-first-command/`, $0.28) to see whether the extra first command disturbs the sequence. It does not: the `grep` ran inside the first command, the first edit is a design-only docstring, the second is a single end-to-end test, the code is split into `studyconfig.py`, `fit.py` and a thin `study.py`, existing code is untouched, no corrections were needed, and the report ends with the setup line. **But all tests went into one file** (`test_study.py`), where the three 0.4.3 runs each wrote a test file per part. One run cannot show whether 0.4.4 caused this or it is run-to-run variation.
- Not tested: Codex and `AGENTS.md`; one to two runs per scenario.

## Routing with a one-line rule in the project's CLAUDE.md — 2026-11-14

`routing.py --user-setup --project-rule TEXT`: the same 12 prompts and the same real setup as the section below (81 skills listed), with one addition: each fixture copy holds a `CLAUDE.md` containing only this rule, loaded as project instructions.

> Before changing research or experiment code in this repository (training, evaluation, losses, metrics, data, simulations, experiment runners, or their tests), load the research-engineering-code skill and follow it. Not needed for questions with no code change, throwaway scripts, or dependency and config chores.

Results in `outputs/research-engineering-code-eval/2026-11-14-routing-project-rule/`. Cost $1.21.

| Setup | Should trigger | Should not trigger |
| --- | --- | --- |
| User's own setup, description only | 2/8 | 0/4 |
| User's own setup, plus the rule in the project's `CLAUDE.md` | 8/8 | 0/4 |

- **The rule fixes routing in this test.** Every request the skill should cover loaded it as the first action, and none of the four it should stay out of did, including the dependency bump, which edits a file.
- The session transcripts confirm the rule text reached all 12 sessions and that the skill loaded was this one.
- One run per prompt on Sonnet, on the two fixtures. The same rule in the user's global instructions was not tested; there it would apply to every project, and its "in this repository" wording would need changing.

## Opus spot check on c09i — 2026-11-14

Three interactive runs of `c09i-config-runner` with 0.4.3 on Opus (executor only; simulated user and judge on Sonnet), isolated setup, in `outputs/research-engineering-code-eval/2026-11-14-opus-c09i-0.4.3/`. Cost $2.11 including the judge.

| Measure | r1 | r2 | r3 |
| --- | --- | --- | --- |
| Loaded the skill unprompted | yes | yes | yes |
| First edit is a design-only docstring ending in `Existing output changed: none` | yes | yes | yes |
| Second edit is the end-to-end test file | yes (6 tests) | yes (6 tests) | yes (5 tests) |
| Thin whole written, then run, before any part test | yes | yes | yes |
| Then one part per edit, tests run after each (config, data, train) | yes | yes | yes |
| Modules: `config.py`, `data.py`, `train.py`, thin `run.py`, each with a matching test file | yes | yes | yes |
| Hidden tests: required / protection / existing | 3/3, 5/5, 2/2 | 3/3, 5/5, 2/2 | 3/3, 5/5, 2/2 |
| Existing training output unchanged; seeding bug reported, not fixed | yes | yes | yes |
| User corrections / questions asked | 0 / 0 | 0 / 0 | 0 / 0 |
| Tests added | 21 | 23 | 24 |
| Mutation score (visible mutants) | 0.86 | 1.00 | 0.80 |
| Judge: structure / readability | 4 / 5 | 4 / 5 | 4 / 4 |

- **Opus follows the whole sequence**, including one part per edit, which Sonnet followed only partly on the larger probe.
- **Opus reuses existing code instead of copying it.** All three runs moved the training loop into a shared function and rewired the existing `train()` onto it, checking its output against a saved baseline first. Existing source files therefore changed (`data.py`, `train.py`), with results verified identical; the hidden existing-behaviour tests pass.
- **One unrequested behaviour in 3/3:** the command refuses to run into a directory that already holds `metrics.json`. The agent treats it as a protection (an earlier result would be overwritten silently); the judge counts it as a capability nobody asked for. It makes rerunning the same command fail, which a user may not expect. A README section was also added in 3/3.
- The end-to-end step is a file of five or six tests, not the single test the skill asks for.
- **Limits.** No Opus run without the skill exists in this format, so this shows the skill is followed on Opus, not how much it adds there. The Sonnet runs on c09i used 0.4.1 and 0.4.2, so the two models are not compared on the same version. One case, three runs.

## Routing with the user's own setup — 2026-11-14

`routing.py --user-setup`: the same 12 prompts, one run each, Sonnet, with the user's own settings, global instructions, plugins and skills loaded (81 skills listed at start-up; one plugin whose hook drops headless prompts was switched off for these sessions). Results in `outputs/research-engineering-code-eval/2026-11-14-routing-real-setup/`. Cost $1.05.

| Setup | Skills listed | Should trigger | Should not trigger |
| --- | --- | --- | --- |
| Isolated, two earlier rounds | 17–19 | 6/8, 5/8 | 0/4, 0/4 |
| User's own setup | 81 | 2/8 | 0/4 |

- **Routing is much weaker in real use.** Two of eight requests the skill should cover loaded it.
- **The two that loaded it are the two Chinese prompts, and both are close to examples quoted in the description** ("给训练加早停", "重构一下但结果不能变"). The English prompts did not load it, including "Write proper tests for tinylab.metrics", which is also close to a quoted example. Recall on unseen wording is therefore not shown to be above zero here.
- **The description was not cut.** The session transcripts show it in full in the start-up listing, so the cause is not truncation. No other skill was loaded in its place: the agent went straight to the shell.
- One run per prompt; the difference from the isolated rounds is large enough to act on, the exact rate is not established.
- Not separated: how much of the drop comes from the longer skill list and how much from the user's global instructions, which load in the same setup.

## 0.4.3 probe: one module per part — 2026-11-14

Change under test (0.4.3, `SKILL.md` `4f92738aba0ae6ad`; 0.4.2 preserved in [variants/previous-0.4.2](variants/previous-0.4.2)): the design names the file each part lives in; each part that would be tested on its own gets its own module with a matching test file, and the entry module stays a thin shell; after the thin end-to-end version, each later edit adds one part's tests. The "sentence or two" before a change inside existing code is removed (never followed, no effect on outcomes). Probe case `p01-lr-study`, three runs, Sonnet, in `outputs/research-engineering-code-eval/2026-11-14-probe-0.4.3-modules/`. Cost $0.96.

| | 0.4.0 | 0.4.1 | 0.4.3 |
| --- | --- | --- | --- |
| First edit is a design-only docstring | 0/3 | 2/3 | 3/3 |
| Second edit is an end-to-end test | 0/3 | 2/3 | 3/3 |
| New modules (excluding tests) | 1 each | 1 each | 4 each: config, training, summary, thin entry module |
| Matching test file per part | no | no | 3/3 (one run has no separate config test file) |
| Largest new module | 157–170 lines | 159–208 lines | 91–94 lines (the entry module) |
| Existing training code changed in turn 1 | 2/3 | 1/3 | 0/3 |
| User corrections | 0, 1, 1 | 1, 0, 0 | 0, 0, 0 |

- **Structure now follows the design.** Every run split the work into one module per responsibility with matching test files, the layout the user set out to get.
- **One part per edit is mixed.** One run wrote each module as its own edit; one wrote the tests for one part separately and the rest in a batch; one wrote all modules in one edit and all part tests in the next. The thin whole still arrives as a single step.
- The judge marked run 1's design as missing although its first edit is a design-only docstring; the deterministic reading of first edits is the reliable one here.
- Three runs on one case.

## Four older cases aligned — 2026-11-14

c03i, c10i, c11i and c07i now use purpose-only briefs and categorised hidden tests (c03i: two protection tests on NumPy's global random state; c10i accepts any raised error for "fail loudly"; c11i and c07i: existing-behaviour tests). Each was checked against throwaway workspaces: the reference passes everything, the untouched fixture fails the required tests, and the loophole fails on the intended test (global reseed in c03i; returning 0.0 in c10i; fixing the seeding bug in c11i; adding a test file in c07i). None of these four has been run against a model under the current skill.

## 0.4.2 check on c09i — 2026-11-14

Change under test (0.4.2, `SKILL.md` `a8d05198e25fe094`; 0.4.1 preserved in [variants/previous-0.4.1](variants/previous-0.4.1)): the design's "Outside" part ends with a line `Existing output changed:` naming every existing command or function whose results would differ, or `none`. If it is not `none`, that is the one place to ask before making the change. Three runs on c09i, Sonnet, in `outputs/research-engineering-code-eval/2026-11-14-c09i-0.4.2/`. Cost $0.85.

| c09i | baseline | 0.4.0 | 0.4.1 | 0.4.2 |
| --- | --- | --- | --- | --- |
| First edit is a design-only docstring | 0/3 | 0/3 | 3/3 | 3/3 |
| Existing training output changed without asking | 3/3 | 3/3 | 3/3 | 0/3 |
| User corrections per run | 1 | 1 | 1 | 0 |
| Required / protection / existing hidden tests | 3/3, 14/15, 6/6 | all pass | all pass | all pass |
| Tests added / mutation score | 2 / 0.53 | 7 / 0.79 | 8.3 / 0.84 | 9.3 / 0.83 |

All three designs carried the line with `none` and were built to keep it true. One run left the existing files untouched, gave the runner its own seeded batching, and reported the bug. Two runs edited the existing code only by adding opt-in arguments, with the defaults and the recorded training numbers unchanged (both existing-behaviour tests pass). No run needed a correction. Three runs on one case; a signal, not a measurement.

Still open after 0.4.2: building one behaviour at a time does not happen; everything goes into one module; for a change inside existing code the one-sentence design is not written; routing is about 70% (11 of 16 over two rounds) in an isolated setup with 19 skills.

## 0.4.1 pilot — 2026-11-14

0.4.1 (`SKILL.md` `c5a4ad99d994b599`) on c09i and m01i, 3 runs each, Sonnet, in `outputs/research-engineering-code-eval/2026-11-14-pilot-0.4.1/`. Cost $2.05. Baseline and 0.4.0 figures are from the 0.4.0 pilot below (same cases, prompts, briefs and hidden tests; only the judge's definition of "design before editing" changed, to accept a design-only first edit). Routing was not rerun: the description is unchanged since 0.4.0.

| c09i (new command) | baseline | 0.4.0 | 0.4.1 |
| --- | --- | --- | --- |
| Required / protection / existing hidden tests | 3/3, 14/15, 6/6 | 3/3, 15/15, 6/6 | 3/3, 15/15, 6/6 |
| First edit is a design-only docstring | 0/3 | 0/3 | 3/3 |
| Second edit is a test | 0/3 | 0/3 | 3/3 (a single end-to-end test in 2) |
| Seeding bug fixed without asking, undone on objection | 3/3 | 3/3 | 3/3 |
| User corrections per run | 1 | 1 | 1 |
| Tests added / mutation score | 2 / 0.53 | 7 / 0.79 | 8.3 / 0.84 |
| Judge structure / readability | 3.3 / 3.7 | 4.0 / 4.0 | 4.0 / 4.0 |
| Cost per run | $0.21 | $0.35 | $0.40 |

| m01i (change inside existing code) | baseline | 0.4.0 | 0.4.1 |
| --- | --- | --- | --- |
| Hidden tests | all pass | all pass | all pass |
| Skill loaded | n/a | 3/3 | 2/3 |
| `--dt` bug fixed without asking | 3/3 | 0/3 | 1/3 (the run where the skill did not load) |
| A sentence on what changes before editing | 0/3 | 0/3 | 0/3 |
| User corrections per run | 1 | 0 | 0.33 |

Findings:

- **Design first now holds on new pipeline-level work:** 3 of 3 on c09i, with short, accurate docstrings (purpose, how it is run, parts and data flow).
- **The seeding bug is still fixed without asking on c09i, in every version except 0.3.0.** The agents reuse the existing training code, judge that "reproducible runs depend on it", and report the change clearly afterwards. One 0.4.1 design even states that `tinylab.train` "keeps its flags and behaviour" and then changes its numbers. This is the skill's own stop condition (a change to results someone relies on) not being applied.
- **For a change inside existing code the "sentence or two" is not written** (0 of 3 on m01i). The outcome there is good regardless.
- **One m01i run did not load the skill**, and behaved like the baseline.
- **Not built one behaviour at a time** in any run.
- Small numbers: three runs per cell.

## 0.4.1 probe: design as the first edit — 2026-11-14

Change under test (0.4.1, `SKILL.md` `c5a4ad99d994b599`; 0.4.0 preserved in [variants/previous-0.4.0](variants/previous-0.4.0)): sections 1 and 4 turn the workflow into actions. For a new module, command or pipeline the first edit creates the entry module holding only a header docstring with the design (purpose, outside, inside); the next edit is one end-to-end test; then the thinnest implementation; then one behaviour at a time. Same probe case and setup as the 0.4.0 probe below; results in `outputs/research-engineering-code-eval/2026-11-14-probe-design-in-code/`.

| | 0.4.0 probe (3 runs) | 0.4.1 probe (3 runs) |
| --- | --- | --- |
| Design written before any implementation | 0/3 | 2/3 as a docstring-only first edit |
| Design present at the top of the new module | 0/3 | 3/3 |
| Second edit is a test | 0/3 | 2/3 (one end-to-end test in run 1; all nine tests at once in run 2) |
| Built one behaviour at a time | 0/3 | 0/3: the implementation still arrives in one write |
| Existing training code left unchanged in turn 1 | 1/3 | 2/3 |
| User corrections needed | 0, 1, 1 | 1, 0, 0 |
| Where the code went | one new module, 157–170 lines | one new module, 159–208 lines |
| Judge: design / structure / readability | fail ×3 / 4 / 4 | pass ×3 / 4 / 4–5 |

Findings:

- **Phrasing the design as an action worked.** Two of three runs created the entry module with only the design docstring before any code, and one narrated it ("The design goes first, as a header-only module. Next is the end-to-end test through the real entry point."). The third wrote the whole file at once but with the design at its top. Before this change no run of any version had written a design before code.
- **The written "Outside" did its job in the runs that used it.** Run 2's docstring says "tinylab.train and tinylab.data are left unchanged", and that run did not touch them.
- **Incremental building is still not followed.** After the first test, the full implementation is written in one edit and the remaining tests in one batch.
- **Structure is unchanged:** one module holds everything.
- Three runs per variant on one case; treat as a signal, not a measurement. Cost $1.04.

## 0.4.0 probe on a larger task — 2026-11-14

Question: is the design never written before editing because the pilot tasks are too small? Probe case `p01-lr-study` (in [interactive/cases.json](interactive/cases.json), no hidden tests): a learning-rate study with a train/validation split, early stopping, a checkpoint per run, a summary table and resume. Three 0.4.0 episodes, Sonnet, in `outputs/research-engineering-code-eval/2026-11-14-probe-larger/`. The skill loaded in all three.

| | run 1 | run 2 | run 3 |
| --- | --- | --- | --- |
| Visible text before the first edit | 39 characters | 0 | 36 characters |
| Hidden reasoning before the first edit | 307 characters | 231 | 294 |
| Order of work (W = write, R = run) | W W R W R | W R W R W R | W R W R W R W R |
| Where the code went | one new module, 157 lines | one new module, 165 lines | one new module, 170 lines |
| Tests added | 8 | 8 | 10 |
| Seeding bug in existing code | reported, not fixed | fixed, undone on objection | fixed, undone on objection |
| Judge: design before editing / structure / readability | fail / 4 / 4 | fail / 4 / 4 | fail / 4 / 4 |

Findings:

- **Task size is not the explanation.** On a request with five or six responsibilities the agent still wrote no design before editing (0 of 3). It designed in two or three sentences of hidden reasoning and then wrote the whole implementation and its tests in the first write.
- **Not built in steps either.** The first write contained everything; later writes were fixes. The "thin whole, then one behaviour at a time" section was not followed.
- **One module for everything.** All three runs put config checking, the split, training, file output, the summary and the command line into a single new file of about 160 lines, as separate functions. Defensible at this size, but it is not "one module, one responsibility".
- **What did hold:** tests with named purposes, reproducibility and resume covered, assumptions listed, smoke-run numbers labelled as such, and in run 1 an unprompted observation that the validation set is too small to separate the learning rates.
- **Judge noise:** it listed "refuse to reuse results from a changed config" as an unneeded capability while noting that it protects a number. Under the skill's own test that is a protection.
- The judge now retries when its reply is not valid JSON; two of three verdicts had failed to parse.

Conclusion: across five wordings and two task sizes, instruction text has not made the agent write a design before acting or build in steps. Rules phrased as a concrete action (save the output first, write the reproducing test first, report the bug) are followed. Cost of this probe: $0.96.

## 0.4.0 pilot — 2026-11-14

Round in `outputs/research-engineering-code-eval/2026-11-14-pilot-0.4/`. Claude Code 2.1.323, Sonnet throughout. c09i and m01i, baseline and 0.4.0, 3 repetitions each, plus routing. Cost $3.81. The skill loaded in all six 0.4.0 episodes.

The evaluation was first aligned with the goals confirmed that day:

- **Prompts state the interface.** The request now names the command, inputs and outputs, as a real request would. The brief holds only the user's purpose, the existing numbers that must stay, and that no further capabilities are needed. Nothing has to be extracted by questioning.
- **Hidden tests are categorised by name:** required (what the request names), protections (checks it does not name but whose absence lets a wrong result through, such as a mistyped config key or a split with no training data), and existing behaviour. Rejection tests first require a valid run to succeed, so they cannot pass on code that does not run at all.
- **Judge:** design written before editing, structure and readability scores, capabilities the workflow does not need, protections with and without a nameable failure, existing behaviour respected, report against design.
- **Simulated user:** accepts a stated design and assumptions, objects only to contradictions with its brief, accepts protections with a named failure, checks its brief before ending.
- **Mutation filter:** a mutant counts if it breaks a hidden test that passed before, so workspaces missing some hidden tests are still filtered.

| | c09i baseline | c09i 0.4.0 | m01i baseline | m01i 0.4.0 |
| --- | --- | --- | --- | --- |
| Required hidden tests | 3/3 in all runs | 3/3 in all runs | 3/3 in all runs | 3/3 in all runs |
| Protection tests | 14/15 | 15/15 | 3/3 | 3/3 |
| Existing behaviour at the end | kept | kept | kept | kept |
| Changed existing behaviour in turn 1, undone after the user objected | 3/3 (seeding bug) | 3/3 (seeding bug) | 3/3 (`--dt`) | 0/3 |
| User corrections per run | 1 | 1 | 1 | 0 |
| Design written before first edit (judge) | 0/3 | 0/3 | 0/3 | 0/3 |
| Assumptions listed in the first report | 0/3 | 3/3 | 0/3 | 1/3 |
| Structure score (1–5) | 3.3 | 4.0 | 4.0 | 4.0 |
| Readability score (1–5) | 3.7 | 4.0 | 4.0 | 4.0 |
| Capabilities the workflow does not need | 1.0 | 0.67 | 0 | 0 |
| Tests added | 2 | 7 | 2.7 | 2.3 |
| Mutation score | 0.53 | 0.79 | 1.00 | 1.00 |
| Cost per run | $0.21 | $0.35 | $0.20 | $0.17 |

Findings:

- **The design is still not written before editing: 0 of 6**, the same as every earlier version. The agent designs in its hidden reasoning (about 250–300 characters in c09i) and goes straight to editing. Making the design "load-bearing" in the text did not change this.
- **What 0.4.0 did change:** assumptions are listed in the first report (4 of 6, against 0 of 6 for the baseline); on c09i there are more tests and a higher mutation score, with slightly better structure and readability scores; on m01i the `--dt` bug is left alone and reported, with no correction needed.
- **Regression against 0.3.0 on c09i:** all three 0.4.0 runs fixed the seeding bug in turn 1, reasoning that comparing runs needs reproducibility. Under 0.3.0 the agent asked first. The purpose test ("a protection is needed when you can name the failure") pulled against "existing output is the user's decision", and with nothing stopping the agent, the fix went in. A written "Outside: what stays unchanged" would have exposed the conflict, but no design was written.
- **The protection tests barely discriminate:** the baseline passes 14 of 15.
- **Routing: 5/8, no false triggers** (0.3.0: 6/8). One repetition per prompt; the difference is within noise. Across both rounds 11 of 16.
- **Scores are compressed:** structure and readability sit at 3–4 for everything. On tasks this small the judge cannot separate the variants well.

Harness issues found and fixed in this round:

- **Leftover sweep too broad.** It killed any process whose command line mentioned the workspace, including the shell that launched the checker, and would have killed a user's terminal or editor open in a workspace. It now only touches processes that started after the checker and are not its ancestors. Tested both ways.
- **Stale build output.** One baseline m01i run failed every hidden test because `make` kept a binary built during a `git stash` round trip within the same second. The checker now starts from a clean build for fixtures that declare a clean command; the six m01i checks were rerun and the stale ones kept in `superseded/`.

## 0.4.0 — 2026-11-14: draft for review, not evaluated

Target: research-engineering-code 0.4.0, an untracked working copy. No model has been run on it. `SKILL.md` `1152f58535b25a79`, `references/decomposition-example.md` `a25b67394a3f222e`. The 0.3.0 package is preserved in [variants/previous-0.3.0](variants/previous-0.3.0) (`be7c32df6ec1c846`).

Why a redesign and not another patch: over 0.1.0 to 0.3.0 each version answered the last evaluation's findings with more rules, and the skill drifted from its purpose. The user confirmed the goals on 2026-11-14:

- **Two equal first goals:** readable, maintainable code (each module one job, with a test that states it); and trustworthy results (numbers and whole pipeline verified, reproducible, honestly reported).
- **The means:** design the whole first, get a thin real pipeline running, expand gradually.
- **Interaction:** state the design with its assumptions and proceed; stop only when a wrong guess is expensive to undo or changes results someone relies on.
- **Unrequested things:** judged by purpose. A capability only when the stated workflow needs it; a protection whenever the wrong result it prevents can be named.
- **Evaluation:** keep it light.

What 0.4.0 changes against 0.3.0:

- The six sections are one thread: the design decides structure, build order, test names and what the report is checked against.
- The design has five parts: purpose, outside, inside, behaviours, assumptions. The "ask and wait" and "confirm and wait" rules are removed.
- "Build only what was asked" is replaced by the capability and protection tests.
- The structure section cut from 0.3.0 is restored and tied to the design.
- Rules that changed behaviour in the pilot are kept word for word: report bugs outside the request and fix only if asked; save output before a change that must not alter numbers; reproducing test first; no base class, registry or function table for one or two cases.

Executed checks: Skill Creator `quick_validate.py` valid with exactly one `SKILL.md`; `claude plugin validate . --strict` passed; JSON files parse; local Markdown links resolve; repository structure tests (131) pass.

The evaluation material is not yet aligned with these goals. Before any run on 0.4.0:

- Briefs that forbid validation (c09i B7, m01i B7) contradict the protection test and need rewriting around the user's purpose and workflow.
- The judge's "extras beyond request" and "plan before building" items need replacing with the capability and protection tests and "design stated before editing".
- The simulated user should react to a stated design and assumptions, not expect to be asked.
- The known harness faults from the pilot remain: the simulated user's combined reply is dropped when per-question answers exist, and it can end without checking its brief.

## 0.3.0 pilot — 2026-11-14

Round in `outputs/research-engineering-code-eval/2026-11-13-pilot/` (summary.md, summary.csv, every episode's transcript, check and judge). Claude Code 2.1.323 (earlier rounds: 2.1.306), Sonnet for executor, simulated user and judge. c09i and m01i, baseline and current, 3 repetitions each, plus the 12-prompt routing set. Isolation confirmed per episode: 19 skills listed, all built-ins plus the target; the target loaded in all six current episodes. Cost about $9.35 (estimate was $6–7): executors $5.40, simulated user $2.08, judge $0.47, routing $0.51, one superseded smoke episode $0.84.

| | c09i baseline | c09i 0.3.0 | m01i baseline | m01i 0.3.0 |
| --- | --- | --- | --- | --- |
| Hidden tests pass | 3/3 | 2/3 | 3/3 | 3/3 |
| Plan written before first edit (judge) | 0/3 | 1/3 | 0/3 | 0/3 |
| Edited files in turn 1 | 3/3 | 3/3 | 3/3 | 3/3 |
| Question-tool calls per run | 0 | 1 | 0 | 0 |
| User corrections per run | 2.0 | 2.0 | 1.33 | 1.0 |
| Tests added | 3.3 | 6.3 | 2.7 | 4.0 |
| Mutation score (acceptance-visible) | 0.20 | 0.83 (2 runs)* | 1.00 | 1.00 |
| New public names + flags | 6.7 | 5.3 | 3.0 | 3.0 |
| Judge: things built beyond the request | 3.7 | 4.0 | 4.7 | 3.7 |
| `--dt` bug: fixed without asking in turn 1 | | | 3/3 (reverted after the user objected) | 0/3 |
| Pipeline run to save old output before first edit | | | 0/3 | 3/3 |
| Enum or type layer added for two methods | | | 3/3 | 1/3 |

Findings:

- **Plan first is still mostly not followed.** One of six 0.3.0 episodes wrote a plan before editing, against none of six baseline episodes. Counting the superseded smoke episode, which stopped and waited with four open questions, it is 2 of 7. Every episode edited files in turn 1.
- **Questions asked, but not about everything open.** In c09i every 0.3.0 run made one question-tool call holding three or four questions: whether to fix the seeding bug, config format, the split, where results go, the existing flags. None asked what the output files should contain. All kept building in the same turn without confirming the plan. (An interim note during the run said they asked only about the bug; that was read from a truncated first line and is corrected here.)
- **Testing is clearly better with the skill.** c09i: more tests and a much higher mutation score. m01i: more tests at the same score.
- \* Corrected on 2026-11-14 after review: the c09i 0.3.0 run r2 passed no hidden test, so its mutants could not be filtered and its 0.28 was a raw kill rate; the earlier mean of 0.65 averaged it in. The checker now reports no score in that case (`unfiltered_kill_rate` instead), and `summarize.py` leaves such runs out of the mean.
- **Reports are better.** The m01i 0.3.0 reports list assumptions and an explicit "not verified" section.
- **Scope is about the same.** The judge still finds 3–5 unrequested items per run in both variants.
- **One 0.3.0 failure.** The c09i run 2 `metrics.json` lacked `final_loss`. The agent never asked what the output should contain, and was never told: the simulated user wrote the output details into a combined reply that the harness does not forward when per-question answers exist. The simulated user then ended without checking its brief. Attribution: mostly the evaluation harness, partly the agent. (The earlier note that the simulated user had named `final_loss` was wrong.)
- **Routing: 6/8 should-trigger prompts loaded the skill, 0/4 false triggers**, against 1 of 6 in the earlier single-turn runs. Both Chinese should-trigger prompts loaded it; the decaysim integrator check and "write proper tests" did not. Caveat: these sessions list 19 skills, against 83 in the user's own setup.

Harness issues found and fixed during the pilot:

- The edit detector looked only at the first 300 characters of a command, so file writes late in long `python3 - <<…` scripts were missed. That inflated "text before first edit" and hid turn-1 edits. Commands are now checked in full, "edited in turn 1" now comes from the end-of-turn file snapshot, and all 12 episodes were recomputed. The interim figures reported during the run were wrong for that reason.
- The simulated-user rule "at most two brief items per reply" was too strict for replying to an agent that asks four questions. It is now: answer every question asked, make at most two unprompted corrections, never volunteer anything else. The smoke episode under the old rule is kept in `superseded/`.
- Simulated-user fidelity: 2 of about 28 replies were flagged by the judge for correcting too much at once. One answer volunteered items beyond the question it answered and was not flagged. Also, the simulated user ended one episode without noticing a missing output key.
- Routing: the SDK raises an error when a session reaches its turn limit, which is how routing probes stop; this is now treated as a normal stop.

Plan-mode tools (`EnterPlanMode`, `ExitPlanMode`) are available in these sessions. Approval of a plan would pass through the harness's permission callback, so the simulated user could review it.

## 0.3.0 — 2026-11-13: prepared, not yet run

Target: research-engineering-code 0.3.0, an untracked working copy, not committed or registered in `catalog.json`. No model has been run on 0.3.0. Everything below is static checking and validation of the evaluation material.

| File | SHA-256 (first 16) |
| --- | --- |
| `SKILL.md` | `be7c32df6ec1c846` |
| `references/decomposition-example.md` | `a636fb0e41f3afae` |
| `references/test-patterns.md` | `10ed86d49d74fabf` |
| `tests/check_run.py` | `5cc1520ef17cdbc2` |
| `tests/interactive/run_interactive.py` | `1bf1700c3f91f44c` |
| `tests/interactive/run_round.py` | `4361a55b39efed45` |
| `tests/interactive/judge.py` | `a83f6b51b85f61c7` |
| `tests/interactive/summarize.py` | `8e762fefaf664f1e` |
| `tests/interactive/routing.py` | `42d13dade8fe5d28` |
| `tests/interactive/cases.json` | `f4f2a8aa4724d384` |
| `tests/interactive/routing_prompts.json` | `96e46adb8cb605cb` |
| `tests/harness.json` | `8c04b2074af0a34a` |

Fixture tree hashes are unchanged: tinylab `5d4f4979dcfe…`, decaysim `c44c8cdc2fb0…`.

What changed in the skill, against the findings below:

- **Design first was never followed.** Section 1 is now a required plan block before the first edit, with explicit rules for when to ask and wait, confirm and wait, or proceed on stated assumptions.
- **Overbuilding when loaded.** A new section 2 limits scope: everything built must trace back to the request or the confirmed plan. It also says to report unrequested bugs and fix them only if asked, and to do nothing beyond the script for throwaway work.
- **New pipelines.** Section 3: the first code is the thinnest end-to-end path, run before any unit test.
- **Weak routing.** The description is now written in the words users type, including Chinese.
- **Length.** The text is about a quarter shorter (100 to 78 lines). Splitting into behaviours and null controls are kept explicitly.

What changed in the evaluation:

- **Interactive harness is now the primary method.** Added [run_round.py](interactive/run_round.py), [judge.py](interactive/judge.py), [summarize.py](interactive/summarize.py) and [routing.py](interactive/routing.py), all in the repository. The earlier grading scripts lived in a temporary folder that was cleared, and are replaced.
- **Simulated user.** At most two brief items per reply, only to answer a question or correct a direct contradiction. The metrics count replies over the limit, and the judge audits every reply.
- **Scope measure.** `check_run.py` records new public names and new command-line flags.
- **Cases.** Five new interactive cases (m01i, c03i, c10i, c11i, c07i) with briefs, plus a 12-prompt routing set. [eval-plan.json](eval-plan.json) and [scenarios.md](scenarios.md) are rewritten for the interactive method.
- **Snapshots.** The 0.2.0 snapshot is in [variants/previous-0.2.0](variants/previous-0.2.0). Both snapshots keep their skill text as `SKILL.variant.md`, because a nested `SKILL.md` would make the package hold three skills: the skill validator flagged this, and Claude Code can load nested skills. `run_round.py` renames the file in the clean copy it builds. Contents are unchanged: 0.1.0 `61ce3f2c…`, 0.2.0 `55d53a15…`.

Executed checks:

- Skill Creator `quick_validate.py`: valid, with exactly one `SKILL.md`. `claude plugin validate . --strict`: passed.
- The plugin copies `run_round.py` builds for current, previous-0.2.0 and previous-0.1.0 contain no `tests/` and validate. Their remaining warnings are marketplace-submission items (README, license, icon), not loading problems.
- JSON parse of every manifest, plan and case file. Every local Markdown link resolves. ruff passes on the checker and all interactive scripts. Repository structure tests (131) pass.
- Hidden tests for the new cases, against reference, untouched and loophole workspaces built for this check and not kept:

  | Case | Reference | Untouched fixture | Loophole, and the test that catches it |
  | --- | --- | --- | --- |
  | c03i | pass | fail | global reseed in `train`: `test_training_leaves_global_numpy_state_alone` |
  | c10i | pass | fail | returns 0.0 for empty input: `test_empty_input_raises` |
  | c11i | pass | cannot import | also fixes the seeding bug: `test_existing_train_numbers_unchanged` |
  | c07i | pass | fail (no figure) | adds a test file: `test_package_and_tests_untouched` |
  | m01i | pass | fail | unknown method falls back to Euler: `test_pipeline_rejects_unknown_method` |

  No leftover processes in any check. The scope measure lists `balanced_accuracy` for c11i and the three `--method` flags for m01i, as expected.

Not established: everything about model behaviour under 0.3.0, including routing; whether the tighter simulated user behaves as instructed; and the judge's reliability on the new rubric.

## 0.2.0 — 2026-11-12

Target: research-engineering-code 0.2.0, untracked working copy (not yet committed or registered in `catalog.json`).

| File | SHA-256 |
| --- | --- |
| `SKILL.md` | `55d53a158b450b8608bf944eca896317bcaa7aec39668656ffc1532a927b0613` |
| `references/decomposition-example.md` | `ae42b49914b8e1834cacc5ecb63fd83ba13ab68089475bef9ce34cb333a0d802` |
| `references/test-patterns.md` | `10ed86d49d74fabf04ac7d5efa19966cf2eaa964bbb3da67e9e380a6417509ca` |
| `assets/python/pyproject-snippet.toml` | `15e6114c68efb25982c0e1ddae21dfcdcab33c1da4b816e365b2cfdefc3f3457` |
| `assets/python/pre-commit-config.yaml` | `0ed9c90e664c0daa2447400bb79e917c2f81549ad26c412d5ba677d7d56e41a1` |
| `agents/openai.yaml` | `1b3c699f56fd2e8dfc2ac6aceb69d65b8bf8ccc2d09970ff1bd5de67ad9d97a1` |
| `.claude-plugin/plugin.json` | `a7524adc7fd7db7c872630b5647bf9600160c1b32781186c4ab30b7458ed9274` |
| `tests/check_run.py` | `d201f91fb00c3b4e3c22c51e976bbbd28c4f7d429c48c652ef11dd35fb769365` |
| `tests/harness.json` | `6a4720a31c1524984054434ba4a5f59a91c39ca56b054c3a65750cbf5af3f6fe` |

Fixture tree hashes (relative path and content of every file, caches and build output excluded):

- `tinylab`: `sha256-tree:5d4f4979dcfe3e76ba8210eb6bfb4be5346fa313a8538691a2395348c67892ff`, unchanged from 0.1.0.
- `decaysim`: `sha256-tree:c44c8cdc2fb036f9b47f38c7c83d3c79f696b5061f5313fe51969bb0d356fa40`.

The 0.1.0 comparison variant in [variants/previous-0.1.0](variants/previous-0.1.0) is byte-identical to the 0.1.0 files recorded in the previous version of this file (`SKILL.md` `61ce3f2c…`, `decomposition-example.md` `cc8054ad…`, `pytest-patterns.md` `3d38a801…`, both assets unchanged).

## Executed checks

- Skill Creator `quick_validate.py`: frontmatter and scaffold checks passed.
- Claude Code 2.1.306 `plugin validate . --strict`: passed. One advisory, not applied: the README has no marketplace install line, because the package is not in a marketplace yet.
- JSON parse of `plugin.json`, `eval-plan.json` and `harness.json`; every local Markdown link outside the fixtures resolves.
- Repository structure tests (`unittest discover -s tests` with PyYAML provided, 131 tests): OK with this directory present and unregistered. Without PyYAML two test modules fail to import; that is the interpreter, not this package.
- ruff on `check_run.py`: clean.
- decaysim: `make test` passes (2 C checks, 1 unittest). The planted bug reproduces: `./run.sh OUT --dt 0.05 --steps 20` integrates to `final_t = 2.0` instead of 1.0 while its log line reports `dt=0.05`.
- Hidden acceptance tests, against throwaway reference solutions written for this check and not kept in the repository (one per case with a hidden test): all twelve pass, including every `test_pipeline_*` test.
- The same hidden tests against untouched fixture copies: eleven fail or cannot import, as intended. c05 passes by design (behaviour must not change); its separate `actually-restructured` check requires that `train.py` changed and tests were added.
- Loophole solutions, each built to pass the old checks while missing the request:

  | Loophole | Caught by |
  | --- | --- |
  | c01: `--label-smoothing` parsed but not passed to `train` | `test_pipeline_flag_reaches_training`, `test_pipeline_rejects_smoothing_outside_unit_interval` |
  | c03: `np.random.seed(seed)` inside `train` | `test_training_leaves_global_numpy_state_alone` |
  | c04: prints deleted, nothing logged | `test_train_progress_goes_to_package_loggers` |
  | c05: nothing changed | acceptance passes; the change record shows no modified source and no tests added |
  | m02: nothing changed | `test_pipeline_halved_step_reaches_the_same_time`, `test_pipeline_error_halves_with_the_step` |
  | c01: skip marker on an existing test, root `conftest.py`, `addopts` in `pyproject.toml`, `src/sitecustomize.py` | `tests.skip_markers_added`, `tests.existing_files_edited`, `files.test_config_changed`, `files.startup_hooks_added`; hidden tests unaffected because they run from a scratch directory |

- Mutation scoring on the references: mutants are generated only on changed lines; mutants the acceptance tests do not notice are excluded; suite errors are counted apart. With all 35 sites, the c01 reference (two thin tests) scores 6 of 19 relevant mutants, with 16 invisible to acceptance. A surviving mutant was checked by hand (a default changed from 0.0 to 1.0, which the reference tests cannot see at even odds). C and shell sources are listed as not mutated.

## Pilot run — 2026-11-12

Configuration: Claude Code 2.1.306 headless (`claude -p`), model `claude-sonnet-5-5`, one repetition, `acceptEdits` with Read, Edit, Write, Glob, Grep, Skill and workspace-scoped Bash (`.venv/bin/python` for tinylab; `make`, `run.sh`, `python3`, `cc` for decaysim), MCP servers off, 4 USD cap and 900 s timeout per run. `current` loaded the package with `--plugin-dir`; `baseline` had no copy of it, and no copy exists in user scope. Every other user skill and plugin (including the Karpathy guidelines) and the user-level CLAUDE.md were present in both variants. The sanctuary-translate plugin was disabled per session because its prompt hook drops headless prompts; this was found by the smoke case. For c07 and c09 the tinylab package was installed editable in the virtualenv so `python -m tinylab.train` works; the c03 pair ran without that, identically for both variants. Grading used `check_run.py` and a blind Sonnet judge with read-only access to a packet with the variant and skill name redacted.

**Routing: the skill was never invoked.** In all four `current` runs the skill appeared in the session's skill list, but no run called it. Implicit triggering failed on 4 of 4 cases, including three where it should fire. The comparison below therefore measures the effect of the skill's listing, not of its rules, and says nothing about whether the rules help once loaded.

| Case | Variant | Hidden tests | Tests added | Mutation score | Judge notes | Cost |
| --- | --- | --- | --- | --- | --- | --- |
| c03 seed | baseline | pass (1/1 pipeline) | 0, so the required check fails | no sites | correct seeded generator | $0.26 |
| c03 seed | current | pass (1/1 pipeline) | 1 end-to-end determinism test | no sites | correct seeded generator | $0.19 |
| c09 runner | baseline | pass (5/5 pipeline) | 3 | 7/10 | no design first, no early end-to-end run, fixed the seeding bug without asking | $0.27 |
| c09 runner | current | pass (5/5 pipeline) | 3 | 8/15 | same as baseline | $0.29 |
| m01 midpoint | baseline | pass (4/4 pipeline) | 2 (C asserts) | 1/1 | noticed the `--dt` bug and reported it without changing results | $0.24 |
| m01 midpoint | current | pass (4/4 pipeline) | 3 (C asserts and unittest) | 1/1 | same as baseline | $0.30 |
| c07 plot | baseline | n/a; `curves.png` produced | 0 | n/a | no ceremony | $0.16 |
| c07 plot | current | n/a; `curves.png` produced | 0 | n/a | no ceremony | $0.16 |

Other observations:

- Sonnet without the skill already solves these cases. The only required-check difference is the missing test in the c03 baseline. With one repetition and no skill loading, that difference is not attributable to the skill.
- Both c09 runs fixed the seeding bug on their own initiative and reported it afterwards. That changes `train` numbers, the behaviour the skill's rule on unrequested bugs is meant to prevent. Both m01 runs did the opposite with the `--dt` bug.
- Both c09 runs skipped an explicit design and an early end-to-end run. c09 is the case where the skill's process rules could make a difference.
- One `current` run called `AskUserQuestion`, which cannot be answered headless; the user-level CLAUDE.md asks for it.
- Three baseline runs wrote scratch files (a check script, two configs) into the session's own temporary directory outside the workspace. No user files were touched.
- Hidden-test change made after observing a run: the c09 wiring test used `lr: 0.0` as its control, which the c09 baseline reasonably rejected. It now uses `1e-4`. c09 is a development case.

Total cost: runs $1.88, judging about $1.06.

### Forced runs — 2026-11-12

Same configuration, `current` package only, with "Use the research-engineering-code skill for this task." prepended to the prompt of c03, c09 and m01. Fresh workspaces with the same environment as the pilot pair for each case. The skill loaded in all three runs as the first tool call. The judge saw the original prompt without the prefix.

| Case | Variant | Hidden tests | Tests added | Mutation score | Judge failures |
| --- | --- | --- | --- | --- | --- |
| c03 seed | baseline / listed / forced | pass / pass / pass | 0 / 1 / 3 | no sites | none / none / none |
| c09 runner | baseline / listed / forced | pass / pass / pass | 3 / 3 / 4 | 7/10 / 8/15 / 9/9 | design first, early end-to-end, smallest surface, independent expected values, unrequested bugs / same / design first, early end-to-end, smallest surface |
| m01 midpoint | baseline / listed / forced | pass / pass / pass | 2 / 3 / 5 | 1/1 each | design first / design first / design first, smallest surface |

What changed when the skill was loaded, from one run each:

- **Tests.** More tests in every case, and better ones. c03 wrote the reproducing test first and confirmed it failed before the fix. m01 saved the Euler output before editing and compared it byte for byte afterwards, then added a convergence-order test. On c09 the suite caught every acceptance-visible mutant (9/9).
- **Reporting.** Each forced run stated what it did not verify, and listed changes to existing behaviour separately.

What did not change, even with the skill loaded:

- **Design first.** No forced run wrote a design before its first edit. c09, a new multi-module pipeline, went straight to editing `data.py`; m01 wrote a one-line intent. This is the central addition of 0.2.0, and it is not followed as written.
- **Early end-to-end run.** c09 wrote every module and its tests before the first run.
- **Unrequested bug.** c09 still fixed the seeding bug without asking, reasoning that the request needed reproducible runs. It disclosed the change clearly.

What got worse:

- **Surface.** Forced m01 added an enum, a parser and a wrapper. Forced c09 added type and range validation beyond the requested key check, and a new `train` parameter. The "fail loudly" rule may be pushing towards extra checks. Lint findings rose slightly (2, 3 and 5 against 0, 0 and 2 for the baseline).

Cost: runs $0.80, judging $0.42.

### Opus repeat — 2026-11-12

The same 11 runs (8 pilot and 3 forced) with `claude-opus-5-5`, in fresh workspaces with the same environment per case, an 8 USD cap per run, and the same Sonnet judge so that grades stay comparable.

| Case | Variant | Skill loaded | Tests added (Sonnet / Opus) | Mutation score (Sonnet / Opus) | Judge failures for Opus |
| --- | --- | --- | --- | --- | --- |
| c03 seed | baseline | no | 0 / 1 | no sites | none |
| c03 seed | listed | no | 1 / 1 | no sites | none |
| c03 seed | forced | yes | 3 / 3 | no sites | none |
| c09 runner | baseline | no | 3 / 4 | 7/10 / 9/14 | design first, early end-to-end, smallest surface, unrequested bugs |
| c09 runner | listed | **yes, implicitly** | 3 / 11 | 8/15 / 13/13 | the same, plus proportionate tests |
| c09 runner | forced | yes | 4 / 14 | 9/9 / 14/14 | design first, early end-to-end, smallest surface, proportionate tests |
| m01 midpoint | baseline | no | 2 / 3 | 1/1 / 1/1 | design first |
| m01 midpoint | listed | no | 3 / 4 | 1/1 / none relevant | design first |
| m01 midpoint | forced | yes | 5 / 6 | 1/1 / none relevant | design first, early end-to-end, smallest surface, split by responsibility, tests survive refactor |
| c07 plot | baseline / listed | no | 0 / 0 | n/a | none / final end-to-end |

Every Opus run passed its hidden tests, and both c07 runs produced the figure without tests.

Findings across both models:

- **Routing.** Implicit loading happened in 1 of 6 should-trigger runs (Opus c09). It never happened under Sonnet.
- **Design first and early end-to-end are not followed by either model**, loaded or not. No forced run on either model wrote any design text before its first edit. Every multi-module run wrote all stages before the first end-to-end run.
- **Loaded on Opus, the skill overshoots.** c09 grew from 4 tests (baseline) to 11 and 22 test functions in the forced run, including parametrised checks for validation the user never asked for. m01 gained a function-pointer abstraction with tests tied to it. The judge flagged surface and proportion each time. The "fail loudly" and two-level verification rules, without a counterweight, appear to read as "validate and test everything".
- **Mutation scores rise when the skill is loaded** (Opus c09 13/13 and 14/14 against 9/14), but partly because there are simply more tests.
- **Unrequested bugs.** Under Opus, c09 fixed the seeding bug in all three variants, and the implicitly loaded run did so with only a brief mention. The m01 runs on both models reported `--dt` and left it alone.
- **Headless context.** The skill says to show the design and ask about unrequested bugs, but nobody can answer in a headless run. Neither model did either.

Cost: Opus runs $5.48 (Sonnet $2.68 for the same 11), judging $1.44.

## Interactive pilot — 2026-11-12

Harness: [interactive/run_interactive.py](interactive/run_interactive.py). The executor is a Claude Agent SDK session (claude-agent-sdk 0.2.180, Claude Code 2.1.306, Sonnet) with `setting_sources=[]`, MCP off and only the target plugin added for the skill variant. Its start-up record lists 17 or 18 skills, all Claude Code built-ins plus the target; none of the user's plugins, skills or global instructions load. A separate Sonnet call plays the user from a private brief ([interactive/briefs](interactive/briefs)), sees only the agent's messages, answers `AskUserQuestion` live through `can_use_tool`, and approves, redirects or ends at each turn end, up to 4 replies. Permissions: writes only inside the workspace or temporary files, no network or package installs.

Case c09i: an open prompt ("run experiments from config files … with a proper train/validation split … somewhere I can compare them later"). The entry point, config keys, outputs, reproducibility, "don't change `tinylab.train`" and scope live only in the brief. The [hidden tests](acceptance/test_c09i_config_runner.py) check only what the brief defines. They pass on a reference, fail on the untouched fixture, fail on a runner that is not reproducible, and fail on a solution that fixes the seeding bug inside `train`.

| | baseline | current |
| --- | --- | --- |
| Skill loaded | no | yes, as the first action |
| Questions asked / design shown before building | none / no | none / no |
| Agent text before first edit | 70 characters | 0 |
| First turn | built an oversized system (run folders, `--set` overrides, a compare tool), changed `train()`'s outputs and fixed the seeding bug | the same pattern (run/compare commands, `runs/` folder, changed `train()` outputs, fixed the bug) |
| User replies needed | 2 redirects, then end | 1 redirect, then end |
| Final state | hidden tests 9/9 (7 pipeline), `train` restored | hidden tests 9/9 (7 pipeline), `train` untouched, bug reported and left |
| Tests added / mutation score | 2 / 3 of 14 | 5 / 8 of 15 |
| Cost (executor + simulated user) | $0.65 + $0.05 | $0.36 + $0.05 |

Findings, from one episode per variant:

- **Even loaded, the skill did not make the agent design or ask first.** Both agents had `AskUserQuestion` available and an open request, and both built straight away. This is the clearest evidence so far that section 1 does not work as written.
- **Both agents overbuilt in the first turn**, the scope problem also seen in the forced runs.
- **After a correction the skill variant recovered faster and better**: one redirect instead of two, more and stronger tests, and the unrequested bug reported and left alone, as the brief wanted.
- The interactive format exposes what single-turn runs could not: how much user effort each variant costs (redirects needed), and how it recovers.

Harness issues found and fixed during the pilot:

- `check_run.py` killed only the direct child on a timeout. During mutation testing of c09 and c09i, mutants that made the runner loop forever left five orphaned `tinylab.run` processes running at full CPU for 6–10 hours, until the user noticed them. They were stopped. Commands now run in their own process group, which is killed on timeout and after exit, and output goes to files so a leftover child cannot hold a run open. A test confirms nothing is left behind in either case. Mutation results already recorded count those mutants as acceptance errors, not catches, so the scores are unaffected.
- Two further safeguards followed:
  - **CPU cap.** Every process the checker starts gets an OS CPU-time limit (`--cpu-limit`, default 300 s). The limit is inherited, so a training run started by a hidden test is capped too, even if it leaves its process group.
  - **Leftover sweep.** Each checker run works inside its own temporary root, which is also the `TMPDIR` for everything it starts. After every command and at the end, it kills any process whose command line or working directory is inside that root or the workspace, and lists them under `leftover_processes` in its record. An empty list means a clean run.
  - Tested: an endless CPU loop is stopped by the cap; a child that escapes its group is found and killed by the sweep; with the sweep switched off, an escaped CPU-burner still dies at the cap.
  - Not usable here: tagging processes through an environment variable. `ps` on this macOS version does not show other processes' environments.

- The first version counted only Edit/Write as edits. Both agents wrote files through shell heredocs. Edits now include shell writes, metrics were recomputed from the saved transcripts with `--recompute`, and the harness now also records which files changed at the end of each turn.
- Simulated-user fidelity:
  - Once, it claimed to have said something that was only in its brief ("I said no validation…"); its instructions now forbid that.
  - Its redirects restate most of the brief at once, so the task is fully specified after one correction. That is realistic for a user correcting an oversized result, but it limits how much later turns can discriminate.

## Author review

`SKILL.md` 0.2.0 and the cases were reviewed by their author against the user's four requirements: scope beyond Python, design first, two-level verification, conditional rules. This is not an independent model run.

## Not established by these checks

- Whether the skill's rules help on balance. Forced runs on two models show more and stronger tests, but also no design-first behaviour and, on Opus, excess tests and surface. Implicit triggering is 1 of 6. Whether 0.2.0 improves on 0.1.0, or behaviours beat atomic functions, is still untested.
- Anything from one repetition per case. The pilot cannot separate variant effects from run-to-run variation.
- Effects outside the two fixture stacks. Python with NumPy, and C with Python and Bash, say nothing about R, Julia, Rust, MATLAB, C++ build systems, notebooks or GPU code.
- Baseline isolation. User-level skills and the globally enabled Karpathy plugin are present on this machine and must be inventoried and held constant across variants before any comparison.
- Items left to the judge: whether c03 keeps shuffling, whether c09 and h02 evaluate on held-out rows, design-first and early end-to-end behaviour, and readability.
- The end-to-end heuristic (`tests.changed_files_reaching_entry_point`) is a pattern match on test files and can miss or over-count.
- Mutation testing covers Python sources only, with small default samples (20 mutants), so scores are noisy.
- Codex discovery, session-local plugin loading, other host versions and other machines.
- The pre-commit template: its hook ids were not executed.
