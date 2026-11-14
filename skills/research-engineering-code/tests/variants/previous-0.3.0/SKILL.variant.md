---
name: research-engineering-code
description: "Use for any change to research or experiment code in any language: training and evaluation loops, losses, metrics, data loading and splits, simulations and solvers, experiment runners and configs, seeding and reproducibility, or tests for any of these. Covers everyday requests such as 'fix this bug in training', 'add X to the model', 'make runs reproducible', 'set up experiments from config files', 'refactor train.py without changing results', '给训练加早停', '修一下这个 bug', '重构一下但结果不能变'. Makes the agent show a short plan before editing, build only what was asked, and verify both the numbers and the end-to-end run. Skip it for questions with no code change, one-off plots or scripts the user calls throwaway, and dependency or config chores."
---

# Research Engineering Code

Experiment code rarely crashes when it is wrong; it produces a plausible number that later becomes a result. Three habits prevent most of that: show a plan before touching files, build only what was asked, and check both the numbers and the whole pipeline.

Scale everything below to the change. The project's own language, layout, test framework and commands always win; do not add tooling unasked. Respond in the user's language.

## 1. Before the first edit, show a plan

This step is required. Before editing any file, write the plan in your reply:

```
Plan
- Change: what will exist afterwards, in one line
- Modules: files or modules touched, one responsibility each
- Data flow and interfaces: how the parts connect; the public functions, commands, file formats or outputs
- Behaviours: the observable behaviours you will build and test
- Out of scope: what you will not build
- Open questions: choices the request does not settle
```

For a local change, such as a bug fix or one function, three lines are enough: Change, Behaviours, Out of scope.

Then decide:

- **Ask and wait** when an open question would change an interface, a file format, an output, or the numbers. Use the question tool if there is one. If you cannot fill in "Data flow and interfaces" without guessing, that is an open question.
- **Confirm the plan and wait** when the work creates or rewires a pipeline (a new command, runner, or multi-stage flow) and someone can answer.
- **Proceed on stated assumptions** when the user has said they cannot answer. List every assumption in the final report.
- **Otherwise proceed.**

## 2. Build only what was asked

- Every new public function, option, flag, config key, check, file and test must trace back to the request or the confirmed plan. Anything else is a suggestion for the report, not code.
- No unrequested validation, abstraction or generality: no base class, registry or function table for one or two cases, and no options "for later".
- Split the work into behaviours a caller can observe, not into as many functions as possible. Private helpers are an implementation detail, tested through the public interface.
- Do not change the behaviour or output of existing code unless the request needs it. Report a bug you find outside the request; fix it only if asked, because a silent fix changes numbers someone may rely on.
- When the user calls the work throwaway, write the script and nothing else: no tests, no package changes.

## 3. New pipeline: thinnest end-to-end path first

When the work creates or rewires a pipeline, the first code you write is the thinnest real path from input to output, through the real interfaces, on tiny input, with the simplest correct version of each stage. Run it before writing unit tests and keep it as an end-to-end test. Then add behaviours one at a time, rerunning it after each.

For a change inside a pipeline that already works, run the existing pipeline before and after the change instead.

## 4. Verify at two levels

- **Numbers.** Test each numerical behaviour against an independent expected value: hand-computed, closed form, or a property such as symmetry or conservation. Add shape, finiteness and edge cases where they matter. Where the code claims an effect, add a null control: a case where the effect must be absent. For a bug fix, first write a test that reproduces the bug and watch it fail.
- **Whole pipeline.** Run it end to end on tiny input through its real entry point.
- **Unchanged numbers.** When results must not change, save the current output before editing and compare it afterwards.
- **Test design.** Test through public interfaces, one behaviour per test. Fit the amount of testing to the risk: a one-line fix gets one or two tests, a new metric a handful.
- **Failing tests.** A failing test is information. Do not delete it, skip it, loosen its tolerance or edit its expected value to make it pass.

Patterns and per-language equivalents are in [references/test-patterns.md](references/test-patterns.md). Worked plans for a local change and for a new cross-language pipeline are in [references/decomposition-example.md](references/decomposition-example.md).

## 5. Keep results trustworthy

- Pass seeds or random generators in explicitly, and leave global random state alone. The same seed and config must give the same result; where bit-exact repetition is impossible, say so and compare within a stated tolerance.
- No silent fallbacks at the boundaries you touch: raise with a message instead of defaulting, broadcasting, or replacing NaN.
- No leakage: splits are disjoint, and normalisation statistics come from the training split.
- Results come only from real runs. Label smoke-run numbers as such.

## 6. Report

End with:
- what changed;
- the actual test and run output;
- what was verified, and at which level;
- the assumptions you made;
- bugs found but not fixed;
- what is still unverified.

Do not describe an experiment outcome you did not run.

For a Python project with no linter configuration, [assets/python/](assets/python) holds a ruff and pytest snippet to offer when the user wants one.
