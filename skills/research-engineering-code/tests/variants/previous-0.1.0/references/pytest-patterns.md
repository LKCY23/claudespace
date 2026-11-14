# pytest patterns for experiment code

Short patterns for the rules in SKILL.md. The examples use NumPy; with PyTorch, replace `np.testing.assert_allclose` with `torch.testing.assert_close` and seed a `torch.Generator`.

## Known value from an independent source

```python
def test_uniform_logits_give_log_num_classes():
    logits = np.zeros((4, 3))            # every class equally likely
    targets = np.array([0, 1, 2, 0])
    assert cross_entropy(logits, targets) == pytest.approx(math.log(3))
```

The expected value comes from reasoning about the case, not from the code under test.

```python
# Avoid: the test recomputes the answer the way the code does, so it cannot fail.
def test_cross_entropy():
    expected = -np.log(softmax(logits))[np.arange(4), targets].mean()
    assert cross_entropy(logits, targets) == pytest.approx(expected)
```

## Properties when no literal is handy

```python
def test_accuracy_is_invariant_to_sample_order():
    perm = np.random.default_rng(0).permutation(len(labels))
    assert accuracy(preds[perm], labels[perm]) == accuracy(preds, labels)
```

Useful properties: symmetry, invariance to order or batch split, zero when inputs are equal, outputs sum to one, monotonic in a parameter.

## Null control

```python
def test_smoothing_zero_matches_unsmoothed_loss():
    assert cross_entropy(logits, targets, label_smoothing=0.0) == pytest.approx(
        cross_entropy(logits, targets)
    )

def test_shuffled_labels_give_chance_accuracy():
    rng = np.random.default_rng(0)
    labels = rng.integers(0, 2, size=2000)
    preds = rng.integers(0, 2, size=2000)   # independent of labels by construction
    assert accuracy(preds, labels) == pytest.approx(0.5, abs=0.05)
```

## Determinism

```python
def test_same_seed_gives_same_batches():
    first = list(iterate_batches(data, batch_size=2, rng=np.random.default_rng(7)))
    second = list(iterate_batches(data, batch_size=2, rng=np.random.default_rng(7)))
    for a, b in zip(first, second, strict=True):
        np.testing.assert_array_equal(a, b)

def test_different_seeds_give_different_order():
    first = np.concatenate(list(iterate_batches(data, batch_size=2, rng=np.random.default_rng(7))))
    second = np.concatenate(list(iterate_batches(data, batch_size=2, rng=np.random.default_rng(8))))
    assert not np.array_equal(first, second)
```

Pass the generator in. A function that calls the global `np.random` or `random` cannot be tested this way and is not reproducible either.

## Shape and finiteness

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

Match on a word from the message so the test fails if a different error is raised for a different reason.

## Restoring global state

```python
@pytest.fixture(autouse=True)
def _restore_environment(monkeypatch):
    """Undo environment changes after each test in this file."""
    monkeypatch.delenv("EXPERIMENT_SEED", raising=False)

@pytest.fixture
def clean_registry():
    """Give the test an empty registry and put the original entries back."""
    saved = dict(REGISTRY)
    REGISTRY.clear()
    yield REGISTRY
    REGISTRY.clear()
    REGISTRY.update(saved)
```

Save before `yield`, restore after it. Do the same for logger handlers and levels, default dtype, and any module-level cache. Use `monkeypatch` for environment variables and attributes, because it restores them for you.

## Files

```python
def test_save_then_load_returns_equal_metrics(tmp_path):
    path = tmp_path / "metrics.json"
    save_metrics({"accuracy": 0.75}, path)
    assert load_metrics(path) == {"accuracy": 0.75}
```

Always `tmp_path`; never the repository or the home directory.

## Smoke test for orchestration

```python
def test_training_smoke_run_produces_finite_loss(tmp_path):
    config = Config(steps=3, batch_size=2, seed=0, output_dir=tmp_path)
    history = train(config, data=tiny_dataset())
    assert len(history) == 3
    assert all(math.isfinite(loss) for loss in history)
```

Three steps on a handful of samples. It checks the wiring, not the science; do not assert that the loss decreased unless the setup makes that certain.

## Markers

```python
@pytest.mark.slow
def test_full_epoch_matches_reference_curve(): ...
```

Register `slow` and `gpu` in the pytest config and exclude them by default, so the suite a developer runs after every change finishes in seconds.

## Tolerances

Use `pytest.approx` or `assert_allclose` with a tolerance justified by the arithmetic (float32 around `1e-6`, accumulated sums looser). Widening a tolerance until a failing test passes hides a bug.
