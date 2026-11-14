# Worked examples: design, thin whole, behaviours

Read this when unsure how much design a task needs, what belongs in it, or how fine to slice the work. The first example is a local change in a Python and NumPy repository; the second is a new pipeline that crosses a language boundary. The reasoning is the same in any language.

## Example 1: a local change to a working pipeline

> Add label-smoothed cross-entropy and let the trainer use it through the config.

### Design

A change this size sits inside existing code, so in practice nothing is written down first and the work goes straight to the first test. The design is spelled out here to show the reasoning.

**Purpose**: train with label smoothing and compare against unsmoothed runs, so smoothing must be switchable from the config and zero smoothing must reproduce today's numbers.

**Outside**: one new config field, `label_smoothing` (default 0.0). With the default, every existing run gives the same loss history as before. `Existing output changed: none`.

**Inside**

- `losses` (numerical core): computes losses from logits and integer targets.
- `config` (boundary): gains the field.
- `train` (orchestration): passes the configured value to the loss.

Data flow: config file → `Config.label_smoothing` → `train` → `cross_entropy(..., label_smoothing)` → loss history. One interface changes:

```python
def cross_entropy(logits: np.ndarray, targets: np.ndarray, label_smoothing: float = 0.0) -> float: ...
```

Smoothing is a parameter of the existing loss, not a second loss, because callers should not have to choose between two names that differ by one number.

**Behaviours**

1. `uniform_logits_give_log_num_classes` (known value: every class equally likely, so the loss is `log K`)
2. `confident_correct_prediction_gives_near_zero_loss`
3. `smoothing_zero_matches_unsmoothed_loss` (null control: the new term must vanish)
4. `smoothing_raises_loss_of_a_confident_correct_prediction`
5. `uniform_logits_are_unaffected_by_smoothing` (known value: still `log K`)
6. `rejects_smoothing_outside_zero_one`
7. `training_smoke_run_with_smoothing_produces_finite_loss`

**Assumptions**: smoothing spreads mass uniformly over all classes, including the target class (the common definition). Nothing here is expensive to undo, so the work proceeds.

### What belongs, and what does not

- A smoothing schedule or a second loss function: capabilities. No step of "train with smoothing and compare" fails without them, so they are left out and mentioned as suggestions.
- Behaviour 6, rejecting smoothing outside [0, 1]: a protection. The failure it prevents has a name: a smoothing of 1.5 gives negative target probabilities and a loss that still looks like a number.
- Validating that logits are finite on every call: no named failure that the existing training checks do not already catch, so it is left out.

### Building it

The pipeline already runs, so it is the thin whole: run it once before starting, saving the loss history, and again after each step. Behaviours 1 to 6 are fine-grained because a wrong loss does not crash, it just trains a slightly different model. Behaviour 7 is the only test of the trainer change, because wiring errors usually do crash and one tiny run exposes them.

```python
def cross_entropy(logits, targets, label_smoothing=0.0):
    _check_inputs(logits, targets, label_smoothing)
    log_probs = _log_softmax(logits)
    target_dist = _smoothed_one_hot(targets, logits.shape[1], label_smoothing)
    return float(-(target_dist * log_probs).sum(axis=1).mean())
```

Three private helpers, each a few lines. They keep the public function readable. None gets its own test: behaviours 1 to 6 exercise all of them, and they can be renamed, merged or inlined without touching a test.

### The slicing to avoid

Splitting into the smallest possible functions and testing each one produces this:

```
test_log_softmax.py          # asserts on _log_softmax
test_smoothed_one_hot.py     # asserts on _smoothed_one_hot
test_reduce_mean.py          # asserts on a one-line wrapper
test_check_inputs.py         # asserts on a private validator
```

Four files, and the question a researcher cares about, "is the loss right?", is still unanswered. Every later refactor of the internals breaks tests while the behaviour is unchanged, which teaches everyone to ignore red tests.

A helper earns its own public name and tests in two cases. `_log_softmax` becomes `log_softmax` once a second caller appears, say a calibration metric. And a running-statistics accumulator inside a metric is numerical logic where an off-by-one in the count gives a believable but wrong mean, so it gets known-value tests even with one caller.

### The report

The report walks the design: each of the seven behaviours with its test output; the before-and-after loss histories at zero smoothing, identical; the assumption about the smoothing definition; the two capabilities left out.

## Example 2: a new pipeline across a language boundary

> Our random-walk simulator is in C. Add a Python step that reads its output and reports the mean squared displacement against theory, and a script that runs both.

### Design

This is a new pipeline, so the design is the first edit: `run.sh` is created holding only this header comment, before any code.

```bash
#!/usr/bin/env bash
# Purpose: check the random-walk simulator against theory before trusting larger runs.
# Outside: ./run.sh OUT --steps S --walkers W --seed K
#          writes OUT/walks.csv and OUT/summary.json (msd, msd_theory).
#          Existing output changed: none
# Inside:  sim (C, unchanged) writes one row per walker: walker,final_position
#          analysis/walks.py reads that CSV and checks its columns (the only boundary)
#          analysis/msd.py computes MSD and its theoretical value from positions, S, sigma
#          analysis/summarize.py parses arguments, calls the two, writes summary.json
#          run.sh builds, simulates, runs summarize.py
```

The same design, with the reasoning behind it:

**Purpose**: check the simulator against theory, by eye and in a test, before trusting larger runs.

**Outside**: `run.sh OUT --steps S --walkers W --seed K` writes `OUT/walks.csv` and `OUT/summary.json` with `msd` and `msd_theory`. The C simulator and its output are unchanged, so the last line reads `Existing output changed: none`. Had it named anything, that would be the one thing to ask about before building.

**Inside**: `sim` (C, unchanged: writes one row per walker), `analysis/walks.py` (boundary: reads the CSV and checks its columns), `analysis/msd.py` (numerical core: MSD and its theoretical value), `analysis/summarize.py` (thin shell: arguments in, `summary.json` out), `run.sh` (orchestration: build, simulate, analyse). The reader and the computation are separate modules because each has a behaviour worth testing on its own; the shell has none beyond the end-to-end run, so it gets no test file.

Data flow: `run.sh` → `sim` writes `walks.csv` with header `walker,final_position` → `walks.py` reads it → `msd.py` computes from the positions, plus `S` and `sigma` from the command line → `summarize.py` writes `summary.json`. The boundary is the CSV file: its columns are named in one place on each side and checked where Python reads it.

**Behaviours**

1. `pipeline_writes_summary_with_msd_and_theory` (end to end, tiny run)
2. `msd_of_known_positions_matches_hand_value`
3. `theory_is_steps_times_sigma_squared`
4. `reader_rejects_file_without_final_position_column`
5. `large_run_msd_is_within_three_standard_errors_of_theory` (known-answer statistical check, marked slow if it takes more than a second)

**Assumptions**: `summary.json` sits next to the CSV in `OUT`; `sigma` is the simulator's fixed step size, passed as a flag with that default. Both are cheap to change later, so they are stated and the work proceeds. Had the request needed a change to the simulator's noise model, every existing set of walks would change; that would be worth stopping to ask about.

### What belongs, and what does not

- A plot of MSD against steps: a capability. The purpose is met by the two numbers, so it is a suggestion.
- Behaviour 4: a protection. Named failure: if the C side renames the column, the reader would otherwise fail obscurely or, worse, read the walker index as a position.
- Behaviour 5: a protection. Named failure: if the C side scaled the noise wrongly, every unit test on the Python side would pass and the reported MSD would be wrong.

### Order of work

1. After the header comment, write test 1: `run.sh` on 10 walkers and 5 steps must produce a `summary.json` with both numbers. Then fill in `run.sh` and the three Python modules, each with its simplest correct version, until it passes. The format, paths and arguments are now proven to fit before any detail is polished.
2. Then one part per edit, test first, in the project's Python test runner: the tests for `msd.py` (behaviours 2 and 3) with whatever code they show is missing, then the tests for `walks.py` (behaviour 4). Rerun test 1 after each.
3. Add behaviour 5 last. It is the check that ties the two languages together numerically.

No new C tests are needed, because the C code did not change. If it had, its tests would use whatever the C side already uses, not a new framework.

## Observing state without reaching inside

Boundary modules often configure global state, such as the logging setup. Prefer asserting on return values and written files. When the state itself is the contract, expose a small read-only query in the module (`configured_level()`, `handler_count()`) and test through it, so tests never import private names or inspect the internals of another library.
