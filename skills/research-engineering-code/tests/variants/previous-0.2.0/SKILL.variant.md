---
name: research-engineering-code
description: "Write research and experiment code in any language or mixed stack (models, losses, metrics, simulations, solvers, data pipelines, training and evaluation loops, launch scripts, and the config, seeding, I/O and logging around them) so that it stays readable, verifiable and trustworthy: design the modules, data flow and interfaces first, get a minimal real pipeline running end to end, then grow it one behaviour at a time with tests through public interfaces. Use whenever the user asks to implement, extend, restructure, debug or add tests to code in an ML, scientific or simulation experiment repository, even when tests are not mentioned. Do not use for throwaway plotting or analysis scripts, exploratory notebooks, non-research application code, or design discussion without implementation."
---

# Research Engineering Code

Experiment code rarely crashes when it is wrong. It produces a plausible number that later becomes a result, and runs are expensive, so an error found at hour six of a job costs far more than one found by a one-second check. This skill gets the overall shape right first, proves early that the parts fit together, and puts the most careful checks where a silent error would do the most damage.

Treat everything below as defaults to apply with judgment, not as a checklist. Scale them to the change: a one-line fix needs none of the process a new pipeline does. The project's own language, layout, test framework, linters and run commands always win; use what is there and do not introduce new tooling unasked.

Respond in the user's language.

## 1. Design the whole before building parts

Before writing code, read the path the change sits on, from where data enters to where a result comes out. Then write a short design and show it with your plan:

- **Modules** to add or touch, with one line of responsibility each.
- **Data flow**: what passes between stages and in what form (types, shapes, units, file formats), especially across process or language boundaries such as files, command-line arguments, bindings or queues.
- **Key interfaces**: the public functions, commands or file formats that callers and tests will use, as signatures or examples.
- **Behaviour list**: one line per observable behaviour, phrased as a test name, for example `smoothing_zero_matches_plain_cross_entropy`.

Split the work into behaviours, not into as many functions or files as possible. A behaviour is something a caller can observe through an interface: an output, a raised error, a written file, a documented state change. Private helpers are an implementation detail.

Size the design to the task: three lines for a local change, a short page for a new pipeline. Then proceed. Stop to ask only when an open choice would change an interface or the numbers, such as which of two definitions of a metric is meant.

Read [references/decomposition-example.md](references/decomposition-example.md) when unsure how fine to slice.

## 2. Get a thin pipeline running end to end early

When the work creates a pipeline or changes how stages connect, wire the thinnest real path from input to result before deepening any one stage: real modules and real interfaces, tiny data, few steps, CPU, the simplest correct version of each stage. Run it and check that the outputs exist, have the expected shape, units and format, and are finite and plausible.

Keep that run as a fast end-to-end smoke test in the project's test runner, or as a documented command when the stages live in different tools. It proves that the interfaces fit, especially across language boundaries, before effort goes into any one part, and it is rerun after every later step.

When the change is local to one stage of a pipeline that already works, the existing pipeline is the skeleton: rerun it after the change instead of building a new one.

## 3. Grow it one behaviour at a time

Take the next behaviour from the list, write a test that observes it through a public interface, implement it, then rerun the fast tests and the end-to-end check.

- **Test first where it pays most**: numerical core code, and bug fixes, where a test that reproduces the bug comes before the fix. Watch it fail for the right reason. For glue, command-line handling and plotting, a test written right after the code, or the end-to-end check alone, is enough.
- **Do not write all the tests up front.** Tests written in bulk encode a guessed design. The behaviour list is a plan; revise it when the implementation teaches you something, and say so.
- **Spikes are allowed.** When an approach is uncertain, try it quickly, then rebuild what you keep behind tests, and say which parts are which.
- **Code without tests**: when the numbers must stay the same, pin the current output with a characterisation test before changing it.
- **Bugs nobody asked about**: report them. Fix one without asking only when it blocks the requested work and the fix cannot change existing results; otherwise ask, because a silent fix changes numbers someone may already rely on.

## 4. Verify at two levels

Local correctness of the numerical core and global correctness of the pipeline catch different errors. Neither replaces the other.

| Level | What to check |
| --- | --- |
| Numerical core: losses, metrics, estimators, solvers, samplers, anything whose output reaches a result | Fine-grained. Each behaviour gets a known-value case, plus shape, range, finiteness and edge cases. |
| Boundaries: file formats, configs, bindings, seeding, device choice, logging | One test per module through its interface. Round-trip anything that crosses a language or process boundary. |
| Whole pipeline | One end-to-end run on tiny input: outputs exist and are well formed, and where possible a known-answer run, such as synthetic data the model must fit or a simulation that matches a closed-form value. |

Give a helper its own public name and tests only when it has two or more callers, or when it is numerical logic whose wrong value would not raise. Tests aimed at private helpers break on every refactor and leave the real question unanswered.

## 5. Write tests worth keeping

- **Independent expected values**: a hand-computed literal, a closed-form special case, a reference implementation in another tool, or a property such as symmetry, conservation or probabilities summing to one. A test that recomputes the answer with the same formula cannot disagree with the code.
- **Through public interfaces only.** Do not reach into private names or assert on how internals were called. If some state is part of the contract, expose a small read-only query for it.
- **One behaviour per test**, named as a sentence about what the code does.
- **Fast and hermetic by default**: tiny inputs, temporary directories, no network or real dataset. Mark unavoidably slow or hardware-bound tests the way the project does, so the default run stays quick.
- **Restore global state** you touch: random generators, loggers, environment variables, working directory, registries.
- **A failing test is information.** Do not delete it, skip it, loosen its tolerance or edit its expected value to make it pass. If the test itself is wrong, say why before changing it.

Patterns with examples are in [references/test-patterns.md](references/test-patterns.md).

## 6. Keep the structure plain

- **Pure core, thin shell.** Computation takes values and returns values. File and network I/O, argument parsing, device placement and experiment tracking sit at the edges.
- **Pass dependencies in.** Random generators or seeds, devices, configs and paths are arguments, not globals created deep inside.
- **Narrow boundaries between languages and processes**: one documented format or small interface per boundary, validated where it is read.
- **Fail loudly.** No silent fallbacks: a missing config key becoming a default, a shape mismatch broadcasting, a NaN replaced by zero, a missing checkpoint becoming fresh weights, an empty `except`. Raise with a message that says what was expected.
- **One source for anything that changes results**: an explicit config, not literals buried in the computation. Do not add options nobody asked for.
- **Split by responsibility, not by size.** A new module or function earns its place with a distinct job or a second caller. No base class with one subclass, no plugin system, no wrapper that only forwards. Comments explain why, not what.

## 7. Protect research reliability

- **Reproducibility.** Stochastic code takes an explicit seed or generator, and the same seed and config give the same results. Where bit-exact repeatability is not available (nondeterministic GPU kernels, parallel reductions, different hardware), say so and check agreement within a stated tolerance or statistically instead.
- **Numerical sanity** for every new loss, metric or model component: shape, finiteness and at least one known value.
- **Null controls** where the code claims an effect: shuffled labels give chance accuracy, a zero-weight term leaves the loss unchanged, an identity transform returns its input.
- **No leakage.** Splits are disjoint, and normalisation statistics come from the training split only.
- **Evaluation code is core code.** Test a metric against a hand-computed value before trusting a number it produces.
- **Results come only from real runs.** Never hard-code, estimate or fill in a metric, and label smoke-run outputs as smoke runs.

## 8. Finish with an honest report

Run the fast tests, the end-to-end check, and the project's linters if it has them. Then report:

- what was built, with the actual test and run output;
- what was verified at which level, and what is still unverified and why;
- shortcuts or fallbacks left in on purpose, and anything blocked or undecided.

Do not describe an experiment outcome you did not run.

## Tooling

Length, complexity and formatting limits are better enforced by a linter than by judgment, so use the project's configuration. For a Python project that has none, [assets/python/](assets/python) holds a ruff and pytest snippet and a pre-commit config to offer when the user wants them.
