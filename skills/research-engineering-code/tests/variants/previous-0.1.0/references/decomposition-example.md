# Worked example: slicing a task into behaviours

Read this when you are unsure how fine the contract should be. The examples use NumPy; the same reasoning applies to PyTorch or JAX.

## The request

> Add label-smoothed cross-entropy and let the trainer use it through the config.

## The contract

**Modules**

- `losses.py` (numerical core): computes losses from logits and integer targets.
- `config.py` (infrastructure): gains one field, `label_smoothing`.
- `train.py` (orchestration): passes the configured value to the loss.

**Seam**

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
7. `rejects_targets_outside_class_range`
8. `config_rejects_unknown_keys`
9. `training_smoke_run_with_smoothing_produces_finite_loss`

Nine lines, three modules. Behaviours 1 to 7 are fine-grained because a wrong loss does not crash, it just trains a slightly different model. Behaviour 9 is the only test of the trainer change, because wiring errors do crash and one tiny run exposes them.

## What the implementation may look like inside

```python
def cross_entropy(logits, targets, label_smoothing=0.0):
    _check_inputs(logits, targets, label_smoothing)
    log_probs = _log_softmax(logits)
    target_dist = _smoothed_one_hot(targets, logits.shape[1], label_smoothing)
    return float(-(target_dist * log_probs).sum(axis=1).mean())
```

Three private helpers, each a few lines. They keep the public function readable. None of them gets its own test file: all three are exercised by behaviours 1 to 7, and they can be renamed, merged or inlined without touching a test.

## The slicing to avoid

Splitting into the smallest possible functions and testing each one produces this:

```
test_log_softmax.py          # asserts on _log_softmax
test_smoothed_one_hot.py     # asserts on _smoothed_one_hot
test_reduce_mean.py          # asserts on a one-line wrapper
test_check_inputs.py         # asserts on a private validator
```

Four files, and the question a researcher cares about, "is the loss right?", is still unanswered. Every later refactor of the internals breaks tests while the behaviour is unchanged, which teaches everyone to ignore red tests.

## When a helper does earn its own tests

- `_log_softmax` becomes `log_softmax` once a second caller appears, say a calibration metric. Two callers make it a real seam.
- A running-statistics accumulator used inside a metric is pure numerical logic where an off-by-one in the count gives a believable but wrong mean. It gets its own public name and known-value tests even with one caller.

## The loop, for the first two behaviours

1. Write `test_uniform_logits_give_log_num_classes`. Run it: it fails because `cross_entropy` does not accept the input yet, or returns the wrong value. Implement the unsmoothed loss. Run: green.
2. Write `test_confident_correct_prediction_gives_near_zero_loss`. Run it. If it already passes, that is fine for a second known value on the same code path, but note it: a test that has never been red has not shown it can fail. Check it by breaking the code once, for example by flipping a sign.
3. Continue down the list. If behaviour 5 reveals that smoothing changes the uniform case in your implementation, the implementation is wrong, not the list.

## Observing state without reaching inside

Infrastructure modules often configure global state, such as the logging setup. Prefer asserting on return values. When the state itself is the contract, expose a small read-only query in the module (`configured_level()`, `handler_count()`) and test through it, so tests never import private names or inspect the internals of another library.
