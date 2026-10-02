# VERDICT: ml-hardening round 7 — DeepSeek (builder)

**Status:** APPROVED
**Round:** 7

Rewrote the three round-5/round-6 regression tests in `tests/ml/test_hardening.py`
so each fails on the pre-fix commit `147c696` for the *intended* behavioural
reason (an `AssertionError`), not because a helper's return signature changed.
No production code was touched. Only `tests/ml/test_hardening.py` changed.

## How each test now targets its bug

- `test_market_beta_shifted_one_bar_no_lookahead` drives `make_synthetic_matrix`
  (stable public entry point) twice, perturbing one symbol's log-return at bar
  `t` via a `_PerturbingGenerator` that monkeypatches `ml.synthetic_data._rng`.
  Asserts `market_beta` at `t` is unchanged and at `t+1` differs. On `147c696`
  the missing `.shift(1)` makes beta at `t` move → `AssertionError`.
- `test_sparse_cross_sectional_feature_is_neutralised` builds a fixture with a
  feature that varies across symbols on 2/25 timestamps (92% all-NaN) plus a
  dense, varying control feature so neutralisation actually runs. Asserts the
  sparse feature is residualised. On `147c696` the old detector counts the 23
  all-NaN timestamps as constant and misclassifies it market-wide → passed
  through → `AssertionError`.
- `test_fold_local_classification_unchanged_by_future_data` drives the real
  `run_ablation` path. A feature varies across symbols in fold 0's train/val
  windows but is constant in the far future (91% of timestamps), so the
  full-sample classification is market-wide. Flipping only the far-future rows
  to vary flips the full-sample classification while leaving fold 0's train/val
  rows byte-identical. Asserts fold 0's out-of-fold predictions are unchanged.
  On `147c696` the classification is computed on the full matrix, so the flip
  changes fold 0's training features (raw beta vs. residualised ≈ 0) → its
  predictions move from perfect separation to ~0.5 → `AssertionError`.

## Checks run (coordinator's exact commands)

On the pre-fix commit `147c696` (scratch worktree + copied test file):

```
$ git worktree add /tmp/r7check 147c696
$ cp tests/ml/test_hardening.py /tmp/r7check/tests/ml/test_hardening.py
$ cd /tmp/r7check && python3 -m pytest tests/ml/test_hardening.py -q \
    -k "market_beta_shifted or sparse_cross_sectional or fold_local_classification"
```

Result — 3 failed, each an `AssertionError` about the behaviour:

```
>       assert np.isclose(b_orig.iloc[bar_t], b_pert.iloc[bar_t]), (
E       AssertionError: market_beta at bar 50 changed when the return at bar 50 was perturbed — beta is not shifted and leaks the current bar
tests/ml/test_hardening.py:411: AssertionError

>       assert not np.allclose(orig, new), (
E       AssertionError: sparse cross-sectional feature was not residualised — classified as market-wide
tests/ml/test_hardening.py:457: AssertionError

>       assert np.allclose(p_orig, p_alt), (
E       AssertionError: fold-0 predictions changed when only future data was altered — market-wide classification is not fold-local
tests/ml/test_hardening.py:555: AssertionError

FAILED tests/ml/test_hardening.py::test_market_beta_shifted_one_bar_no_lookahead
FAILED tests/ml/test_hardening.py::test_sparse_cross_sectional_feature_is_neutralised
FAILED tests/ml/test_hardening.py::test_fold_local_classification_unchanged_by_future_data
3 failed, 18 deselected, 2 warnings in 7.68s
```

On HEAD:

```
$ python3 -m pytest tests/ml -q -m "not spark and not databricks"
37 passed, 23 warnings in 62.53s
```

## Non-blocking notes

- The fold-local test produces numpy `RuntimeWarning: invalid value encountered
  in divide` from `neutralize_features`'s correlation reporting on a constant
  column; cosmetic only, does not affect the assertion.
- `test_insufficient_coverage_columns_reported` (pre-existing) unpacks the new
  2-tuple return and is HEAD-only; it is excluded by the `-k` filter and is not
  one of the three regressions, so it is left unchanged.

## Scope

- Modified: `tests/ml/test_hardening.py` (commit `d394173`).
- Not touched: `ml/`, `silver/`, `gold/`, `agent/`, `db/`, `api/`, `conftest.py`,
  `pytest.ini`, `requirements*.txt`.
