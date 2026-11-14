---
name: research-engineering-code
description: "Write Python research and experiment code (losses, metrics, models, data pipelines, training and evaluation loops, and the seeding, config, device, logging and registry code around them) so that it stays readable, testable and trustworthy: agree the module seams and a behaviour list first, then build one behaviour at a time behind a failing pytest test. Use whenever the user asks to implement, extend, restructure or add tests to code in an ML or scientific experiment repository, or asks for experiment code with engineering constraints, unit tests or maintainability, even when tests are not mentioned. Do not use for throwaway plotting or analysis scripts, notebooks, non-research application code, or design discussion without implementation."
---

# Research Engineering Code

Experiment code fails differently from product code. It rarely crashes; it quietly produces a wrong number that later becomes a result. Runs are also expensive, so a mistake found at hour six of a GPU job costs far more than one found by a one-second test. This skill keeps the code small and legible, and puts the checks where a silent error would hurt most.

Respond in the user's language. Where the repository already has conventions (layout, test style, linters), follow them; the rules below fill gaps and never override the project.

## 1. Agree the contract before writing code

Write a short contract and show it to the user before the code:

- **Modules** you will add or touch, with one line on what each is responsible for.
- **Seam** of each module: the public functions callers and tests will use, as names and signatures only.
- **Behaviour list**: one line per observable behaviour, phrased as a test name, for example `label_smoothing_zero_matches_plain_cross_entropy`.

A behaviour is something a caller can observe through a public function: a return value, a raised error, or a documented state change. Decomposing the task means splitting it into behaviours, not into as many functions as possible. Private helpers may be as small as readability wants, but they are an implementation detail and are covered through the seam.

Size the contract to the task: a one-function change needs three lines, not a document. Then proceed. Stop to ask only when the request leaves a choice open that would change the seam or the numbers, such as which of two definitions of a metric is meant.

Read [references/decomposition-example.md](references/decomposition-example.md) when unsure how fine to slice.

## 2. Set granularity by the cost of a silent error

| Code | How finely to test |
| --- | --- |
| Numerical core: losses, metrics, statistics, sampling, anything returning numbers that reach a result | Fine. Each behaviour gets a test with a known value, plus shape and finiteness. |
| Infrastructure: seeding, config, device choice, logging, registries | One small module each, tested through its public functions. |
| Orchestration: training loop, launcher, CLI | Coarse. One smoke test on tiny CPU data that runs end to end and checks the outputs exist and are finite. |

Give a helper its own public name and tests only when it has two or more callers, or when it is pure numerical logic where a wrong value would not raise. Tests aimed at private helpers break on every refactor, and pass-through functions add names to read without hiding anything.

## 3. Build one behaviour at a time

Take the next behaviour, write its test, run it and watch it fail for the right reason, write the least code that passes, run the fast suite, then move on.

Do not write all the tests first. Tests written in bulk encode a design you have only guessed at, and they tend to check the shape of things instead of behaviour. The list from step 1 is a plan, so revise it when the implementation teaches you something, and say that you did.

When changing code that has no tests, first pin its current behaviour with a test, then change it.

If you find a bug the request did not mention, report it and ask before fixing it. A silent fix changes numbers someone may already be relying on.

## 4. Write tests worth keeping

- **Independent expected values.** Use a hand-computed literal, a worked example, a closed-form special case, or a property (symmetry, zero when inputs are equal, probabilities sum to one). A test that recomputes the answer with the same formula can never disagree with the code.
- **Through the seam only.** Do not import underscore names or assert on how internal collaborators were called. If a test needs to see state that is part of the contract, expose a small read-only query function.
- **One behaviour per test**, named as a sentence about what the module does.
- **Fast and hermetic.** CPU, arrays of a few elements, `tmp_path`, no network, no real dataset, no GPU. Mark the unavoidable exceptions `slow` or `gpu` so the default run stays quick.
- **Restore global state** you touch: loggers, random generators, environment variables, registries, default dtype. Otherwise test order starts to matter.
- **A failing test is information.** Do not delete it, skip it, loosen its tolerance or edit the expected value to match the output. If the test itself is wrong, say why before changing it.

Patterns for each of these are in [references/pytest-patterns.md](references/pytest-patterns.md).

## 5. Keep the structure plain

- **Pure core, thin shell.** Computation takes values and returns values. File I/O, argument parsing, device placement, logging and experiment tracking sit at the edges. Pure functions are testable in milliseconds; code that opens files and reads globals is not.
- **Pass dependencies in**: the random generator, device, config and paths are arguments, not globals created inside the function.
- **Fail loudly.** No silent fallbacks: a missing config key that becomes a default, a shape mismatch that broadcasts, a NaN replaced by zero, a missing checkpoint that becomes random initialisation, a bare `except`. Raise with a message that says what was expected. A fallback turns a bug into a plausible-looking result.
- **One source for hyperparameters.** Anything that changes results comes from one explicit config object, not from literals inside the computation. Do not add options nobody asked for.
- **Nothing speculative.** No base class with one subclass, no plugin system, no wrapper that only forwards. Functions fit on a screen. A docstring says what in one line; comments are for why.

## 6. Protect the research invariants

- **Determinism.** The same seed and config give the same numbers. For anything stochastic you add, test that two runs with one seed agree and two seeds differ.
- **Numerical sanity** for every loss, metric and model component: output shape, finiteness and one known-value case.
- **Null control.** Where the code claims an effect, add a case where the effect must be absent: shuffled labels give chance accuracy, a zero-weight term leaves the loss unchanged, an identity transform returns its input.
- **No leakage.** Splits are disjoint, and statistics used for normalisation come from the training split only.
- **Evaluation code is core code.** A metric is tested against a hand-computed value before any number it produces is trusted.
- **Results come only from real runs.** Never hard-code, estimate or fill in a metric, and label smoke-test outputs as smoke tests.

## 7. Finish with an honest report

Run the fast suite, and the linter if the project has one. Then report:

- the behaviours implemented and the tests added, with the actual test output;
- what is still untested and why;
- any shortcut or fallback you left in on purpose;
- what is blocked or undecided.

If the project keeps a blockers or open-goals file, update it. Do not describe an experiment outcome you did not run.

## Tooling

Function length, complexity and formatting are better enforced by a linter than by judgment. If the project has none and the user wants them, offer [assets/pyproject-snippet.toml](assets/pyproject-snippet.toml) and [assets/pre-commit-config.yaml](assets/pre-commit-config.yaml). Do not add tooling unasked.
