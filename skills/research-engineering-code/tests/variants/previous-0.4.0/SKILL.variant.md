---
name: research-engineering-code
description: "Use for any change to research or experiment code in any language: training and evaluation loops, losses, metrics, data loading and splits, simulations and solvers, experiment runners and configs, seeding and reproducibility, or tests for any of these. Covers everyday requests such as 'fix this bug in training', 'add X to the model', 'make runs reproducible', 'check why these results look wrong', 'write tests for the metrics', 'set up experiments from config files', 'refactor train.py without changing results', '给训练加早停', '修一下这个 bug', '重构一下但结果不能变'. Makes the agent work from a short design of the whole, build a thin end-to-end path and grow it, add only what the purpose needs, and verify both the numbers and the pipeline. Skip it for questions with no code change, one-off plots or scripts the user calls throwaway, and dependency or config chores."
---

# Research Engineering Code

Research code has one job and two kinds of reader. The job is to produce a result someone will trust, and wrong research code rarely crashes: it returns a plausible number. The readers are the people who will run it and the people who will change it later. So the code has to be right in a way that can be checked, and clear in a way that can be maintained.

Both come from working from a design of the whole. The design decides the structure, the order of building, the names of the tests, and what the final report is checked against. Everything below is that one thread.

Scale it to the change: for a one-line fix the design is one sentence, and the rest is a test and a run. The project's own language, layout, test framework and commands always win; do not add tooling unasked. Respond in the user's language.

## 1. Design the whole first

Read the path the change sits on, from where data enters to where a result comes out. Then, before editing anything, write the design in your reply:

- **Purpose**: the result this code is for, and what the user will do with it.
- **Outside**: how it is run and what comes out (commands, inputs, outputs), and which existing behaviour and numbers stay unchanged. The user will see and depend on this part, so it is theirs to decide.
- **Inside**: the modules, one responsibility each; how data flows between them; the interfaces where they meet.
- **Behaviours**: what a caller will be able to observe. Each becomes a test.
- **Assumptions**: every choice the request left open, and what you chose.

Write it out, because every later step uses it, and a design that stays in your head cannot be corrected by the user or checked at the end. Keep it short: a new pipeline needs all five parts in a few lines each; a local fix needs only what changes and what stays the same.

Then keep working. A user can correct a stated assumption faster than they can answer a question. Stop and ask only when a wrong guess would be expensive to undo or would change results someone already relies on.

Worked designs for a local change and for a new cross-language pipeline are in [references/decomposition-example.md](references/decomposition-example.md).

## 2. Decide what belongs by its purpose

Two kinds of thing can be added, and they are judged differently.

- **A capability** is something the user can newly use: a command, an option, an output, a config key. Build it only if a step of the user's stated workflow fails without it. Otherwise leave it out and suggest it in the report. An unrequested capability is a decision made for the user, and more for them to read and maintain.
- **A protection** is a check, a test, a seed, a comparison. Add it when you can name the wrong result it would otherwise let through silently, for example "a validation fraction of 1.5 leaves the training set empty and the accuracy meaningless". If you cannot name the failure, leave it out. Spend the most protection where a silent error costs the most: on numbers that reach a result.

Changing what existing code outputs is the user's decision too. Report a bug you find outside the request; fix it only if asked, because a silent fix changes numbers someone may rely on. When the user calls the work throwaway, its purpose is a single use: write the script and nothing else.

## 3. Let the structure mirror the design

A reader should be able to find each responsibility from the design in one place in the code, with its tests where the project keeps tests.

- **One module, one responsibility.** Split by responsibility, not by size. A new module or function earns its place with a distinct job or a second caller. No base class, registry or function table for one or two cases.
- **Pure core, thin shell.** Computation takes values and returns values. File and network I/O, argument parsing, device placement and logging sit at the edges.
- **Dependencies are passed in.** Seeds or random generators, configs and paths are arguments, not globals created deep inside.
- **Narrow boundaries** between languages and processes: one documented format or small interface, checked where it is read.
- **Behaviours, not fragments.** Split the work into behaviours a caller can observe, not into as many functions as possible. Private helpers are an implementation detail, tested through the public interface.
- **Names say what; comments say why.**

## 4. Build a thin whole, then grow it

- **New or rewired pipeline.** The first code you write is the thinnest real path through the design's data flow: real interfaces, tiny input, the simplest correct version of each stage. Run it, and keep that run as an end-to-end test. It proves the parts fit before effort goes into any one of them.
- **Then one behaviour at a time.** Take the next behaviour from the design, write its test, make it pass, and rerun the end-to-end test. The whole keeps working after every step.
- **Change inside a working pipeline.** The existing pipeline is the thin whole. Run it before the change, saving its output when numbers must not change, and again after.
- **Bug fix.** First write a test that reproduces the bug and watch it fail.

If building shows the design was wrong, change the design and say so.

## 5. Verify the numbers and the whole

- **Numbers.** Test each numerical behaviour against an independent expected value: hand-computed, closed form, or a property such as symmetry or conservation. Where the code claims an effect, add a null control: a case where the effect must be absent.
- **The whole.** Run the pipeline end to end on tiny input through its real entry point. Where a known answer exists for the tiny case, assert it.
- **Reproducibility.** The same seed and config give the same result, and global random state is left alone. Where bit-exact repetition is impossible, say so and compare within a stated tolerance.
- **No silent wrong values** at the boundaries you touch: raise with a message instead of defaulting, broadcasting or replacing NaN. No leakage between splits.
- **Tests worth keeping.** Test through public interfaces, one behaviour per test, named for the behaviour. A failing test is information: do not delete it, skip it, loosen its tolerance or edit its expected value to make it pass.

Patterns and per-language equivalents are in [references/test-patterns.md](references/test-patterns.md).

## 6. Report against the design

End by checking the result against the design:

- each behaviour, with the actual test or run output that shows it;
- where the result differs from the design, and why;
- the assumptions you made, so the user can correct them;
- capabilities you left out as suggestions, and bugs you found but did not fix;
- what is still unverified.

Results come only from real runs. Do not describe an outcome you did not run, and label smoke-run numbers as such.

For a Python project with no linter configuration, [assets/python/](assets/python) holds a ruff and pytest snippet to offer when the user wants one.
