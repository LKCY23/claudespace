# Test patterns for experiment code

Short patterns for the rules in SKILL.md. Each is stated in general terms, with a Python example where code helps. Write them in whatever test framework the project already uses; the table at the end maps the main assertions to other ecosystems.

## Known value from an independent source

The expected value comes from reasoning about the case, not from the code under test.

```python
def test_uniform_logits_give_log_num_classes():
    logits = np.zeros((4, 3))            # every class equally likely
    targets = np.array([0, 1, 2, 0])
    assert cross_entropy(logits, targets) == pytest.approx(math.log(3))
```

```python
# Avoid: the test recomputes the answer the way the code does, so it cannot fail.
def test_cross_entropy():
    expected = -np.log(softmax(logits))[np.arange(4), targets].mean()
    assert cross_entropy(logits, targets) == pytest.approx(expected)
```

Other independent sources: a closed-form special case (an ODE with an exact solution, a Gaussian with known moments), a value from a trusted library or another language, a published worked example.

## Properties when no literal is handy

Symmetry, invariance to order or batch split, zero when inputs are equal, outputs summing to one, monotonicity in a parameter, conservation of a quantity, convergence at the expected order when a step size halves.

```python
def test_accuracy_is_invariant_to_sample_order():
    perm = np.random.default_rng(0).permutation(len(labels))
    assert accuracy(preds[perm], labels[perm]) == accuracy(preds, labels)
```

## Null control

Where code claims an effect, check a case where the effect must be absent.

```python
def test_smoothing_zero_matches_unsmoothed_loss():
    assert cross_entropy(logits, targets, label_smoothing=0.0) == pytest.approx(
        cross_entropy(logits, targets)
    )

def test_independent_predictions_give_chance_accuracy():
    rng = np.random.default_rng(0)
    labels = rng.integers(0, 2, size=2000)
    preds = rng.integers(0, 2, size=2000)
    assert accuracy(preds, labels) == pytest.approx(0.5, abs=0.05)
```

## Reproducibility

Pass the generator or seed in, then check that one seed repeats and two seeds differ.

```python
def test_same_seed_gives_same_batches():
    first = list(iterate_batches(data, batch_size=2, rng=np.random.default_rng(7)))
    second = list(iterate_batches(data, batch_size=2, rng=np.random.default_rng(7)))
    for a, b in zip(first, second, strict=True):
        np.testing.assert_array_equal(a, b)
```

A function that draws from a hidden global generator can be neither tested this way nor reproduced. Where bit-exact repetition is impossible, as with some GPU kernels or parallel reductions, compare within a tolerance and say why in the test.

## Shape, range and finiteness

```python
def test_forward_returns_one_logit_row_per_sample():
    out = model_forward(params, np.zeros((5, 3)))
    assert out.shape == (5, 2)
    assert np.isfinite(out).all()
```

## Loud failure

```python
def test_rejects_targets_outside_class_range():
    with pytest.raises(ValueError, match="target"):
        cross_entropy(np.zeros((2, 3)), np.array([0, 3]))
```

Match on a word from the message, so the test fails if a different error is raised for a different reason. For a command-line tool, assert a non-zero exit status and a message on stderr.

## Restoring global state

Save before the test, restore after it: random generators, logger handlers and levels, environment variables, the working directory, default dtype, registries, module-level caches. In pytest, `monkeypatch` does this for environment variables and attributes; a fixture with `yield` does it for the rest.

## Files and boundaries

Write to a temporary directory, never the repository or the home directory. For anything that crosses a process or language boundary, test a round trip: what one side writes, the other side reads back unchanged, and a malformed file is rejected with a clear error.

```python
def test_save_then_load_returns_equal_metrics(tmp_path):
    path = tmp_path / "metrics.json"
    save_metrics({"accuracy": 0.75}, path)
    assert load_metrics(path) == {"accuracy": 0.75}
```

## End-to-end smoke test

Run the real pipeline on tiny input, through its real entry point, and check the outputs.

```python
def test_pipeline_writes_finite_metrics(tmp_path):
    subprocess.run(["./run.sh", str(tmp_path), "--steps", "5"], check=True)
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert set(summary) >= {"final_y", "abs_error"}
    assert math.isfinite(summary["abs_error"])
```

It checks the wiring: that every stage runs, the formats match and the outputs are well formed. Do not assert that a loss decreased unless the setup makes that certain. Where a closed-form or known answer exists for the tiny case, assert it; that turns the smoke test into a check of the science as well.

## Slow and hardware-bound tests

Mark them the way the project does (a pytest marker, a CTest label, a separate make target) and leave them out of the default run, so the suite a developer runs after every change finishes in seconds.

## Tolerances

Use a tolerance justified by the arithmetic: float32 around `1e-6`, accumulated sums looser, statistical checks a stated number of standard errors. Widening a tolerance until a failing test passes hides a bug.

## Other ecosystems

| Stack | Approximate equality | Expected error |
| --- | --- | --- |
| Python, pytest | `pytest.approx`, `np.testing.assert_allclose`, `torch.testing.assert_close` | `pytest.raises` |
| C++, GoogleTest or Catch2 | `EXPECT_NEAR`, `Catch::Approx` | `EXPECT_THROW`, `REQUIRE_THROWS` |
| C, plain asserts | `assert(fabs(a - b) < tol)` | check the returned error code |
| Rust | `assert!((a - b).abs() < tol)`, `approx::assert_relative_eq!` | `#[should_panic]`, `is_err()` |
| Julia, Test | `@test a ≈ b atol=tol` | `@test_throws` |
| R, testthat | `expect_equal(a, b, tolerance = tol)` | `expect_error` |
| MATLAB, matlab.unittest | `verifyEqual(a, b, 'AbsTol', tol)` | `verifyError` |
| Shell pipeline | compare outputs with a small script or `diff` | check the exit status |
