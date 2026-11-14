# Worked examples: plan, thin pipeline, behaviours

Read this when unsure how much plan a task needs or how fine to slice it. The first example is a local change in a Python and NumPy repository; the second is a new pipeline that crosses a language boundary. The reasoning is the same in any language.

## Example 1: a local change to a working pipeline

> Add label-smoothed cross-entropy and let the trainer use it through the config.

### Plan

**Modules**

- `losses` (numerical core): computes losses from logits and integer targets.
- `config` (boundary): gains one field, `label_smoothing`.
- `train` (orchestration): passes the configured value to the loss.

**Data flow**: config file → `Config.label_smoothing` → `train` → `cross_entropy(..., label_smoothing)` → loss history. Nothing new crosses a process boundary.

**Key interface**

```python
def cross_entropy(logits: np.ndarray, targets: np.ndarray, label_smoothing: float = 0.0) -> float: ...
```

One public function. Smoothing is a parameter of the existing loss, not a second loss, because callers should not have to choose between two names that differ by one number.

**Behaviour list**

1. `uniform_logits_give_log_num_classes` (known value: every class equally likely, so the loss is `log K`)
2. `confident_correct_prediction_gives_near_zero_loss`
3. `smoothing_zero_matches_unsmoothed_loss` (null control: the new term must vanish)
4. `smoothing_raises_loss_of_a_confident_correct_prediction`
5. `uniform_logits_are_unaffected_by_smoothing` (known value: still `log K`)
6. `rejects_smoothing_outside_zero_one`
7. `config_rejects_unknown_keys`
8. `training_smoke_run_with_smoothing_produces_finite_loss`

**Out of scope**: a second loss, a smoothing schedule, any change to the optimiser.

**Open questions**: none. The request names the loss, the parameter and where it is configured, so the agent proceeds.

The pipeline already runs, so it is the skeleton: run it once before starting and after each step. Behaviours 1 to 6 are fine-grained because a wrong loss does not crash, it just trains a slightly different model. Behaviour 8 is the only test of the trainer change, because wiring errors usually do crash and one tiny run exposes them.

### What the implementation may look like inside

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

### When a helper does earn its own tests

- `_log_softmax` becomes `log_softmax` once a second caller appears, say a calibration metric. Two callers make it a real interface.
- A running-statistics accumulator inside a metric is numerical logic where an off-by-one in the count gives a believable but wrong mean. It gets its own public name and known-value tests even with one caller.

## Example 2: a new pipeline across a language boundary

> Our random-walk simulator is in C. Add a Python step that reads its output and reports the mean squared displacement against theory, and a script that runs both.

### Plan

**Modules**: `sim` (C, unchanged: writes one row per walker), `analysis/msd.py` (numerical core: MSD and its theoretical value), `run.sh` (orchestration: build, simulate, analyse into an output directory).

**Data flow**: `run.sh OUT --steps S --walkers W --seed K` → `sim` writes `OUT/walks.csv` with header `walker,final_position` → `msd.py` reads it plus `S` and `sigma` from the command line → writes `OUT/summary.json` with `msd` and `msd_theory`.

The boundary is the CSV file. Its columns are named in one place on each side and checked where Python reads it: a missing column or a non-numeric value raises instead of being skipped.

**Behaviour list**

1. `pipeline_writes_summary_with_msd_and_theory` (end-to-end, tiny run)
2. `msd_of_known_positions_matches_hand_value`
3. `theory_is_steps_times_sigma_squared`
4. `reader_rejects_file_without_final_position_column`
5. `large_run_msd_is_within_three_standard_errors_of_theory` (known-answer statistical check, marked slow if it takes more than a second)

**Out of scope**: changes to the C simulator, plots, any other statistic.

**Open questions**: should `summary.json` sit next to the CSV or replace an existing summary? Is `sigma` fixed or a flag? Both change an output or an interface, so the agent asks before building and waits for the answers.

### Order of work

1. Write `run.sh` and a `msd.py` that reads the CSV and writes `summary.json` with the simplest correct computation. Run it on 10 walkers and 5 steps. Turn that run into test 1. The format, paths and arguments are now proven to fit before any detail is polished.
2. Add behaviours 2 to 4 one at a time, test first, in the project's Python test runner. Rerun test 1 after each.
3. Add behaviour 5 last. It is the check that ties the two languages together numerically: if the C side scaled the noise wrongly, every unit test could pass and this one would fail.

No new C tests are needed, because the C code did not change. If it had, its tests would use whatever the C side already uses, not a new framework.

## Observing state without reaching inside

Boundary modules often configure global state, such as the logging setup. Prefer asserting on return values and written files. When the state itself is the contract, expose a small read-only query in the module (`configured_level()`, `handler_count()`) and test through it, so tests never import private names or inspect the internals of another library.
