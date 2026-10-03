# BUILD-REQUEST: ml-hardening — ROUND 7 (regression tests, reassigned)

**Branch:** `slice/ml-hardening` · **Builder:** DeepSeek (reassigned from MiMo) · **Validators:** Claude, then Codex

Production code is correct (Codex verified) — **do not change `ml/`**. Only write tests.
Read `.agents/codex/VERDICT-ml-hardening-round5.md` and `BUILD-ml-hardening-round6.md`.

## Why this is round 7

Two rounds of tests have failed to catch the bugs they are named after. The coordinator
ran the current tests against the pre-fix commit `147c696`:

```
test_market_beta_shifted_one_bar_no_lookahead            passes on old code
test_sparse_cross_sectional_feature_is_neutralised       fails on an unrelated ValueError
test_fold_local_classification_unchanged_by_future_data  passes on old code
```

## The three bugs in 147c696 that the tests must catch

1. `ml/synthetic_data.py` (~L177-197): `market_beta` at bar t includes the return at t
   (no `.shift(1)`).
2. `ml/features.py` `_detect_market_wide_columns`: counts all-NaN timestamps as
   "constant", with a 90% threshold — a feature that varies across symbols wherever
   observed but is NaN on >90% of timestamps is classed market-wide.
3. `ml/train.py`: market-wide classification is computed on the **full matrix** before
   the walk-forward loop, so data after a fold's training window can change that fold's
   classification.

## Requirements per test

- Fail on `147c696` with an **assertion** about the behaviour (`AssertionError`), not
  `TypeError`/`ValueError`/unpacking errors. Helper signatures differ between revisions,
  so call stable public entry points or write a small adapter that works on both.
- Fixtures must be large enough that neutralisation runs (symbols per timestamp >
  1 + number of industries), so they do not fail on the cross-section guard.
- Pass on HEAD.

Hints: (1) build the synthetic matrix twice, changing only one symbol's close at bar t;
assert `market_beta` at t is identical and at t+1 differs. (2) feature varies across
symbols on ~5% of timestamps, NaN elsewhere; assert it is residualised (not passed
through unchanged). (3) make the full-sample classification flip by changing only rows
after fold k's training window; assert fold k's training features are identical.

## The exact check the coordinator will run — run it yourself first

```bash
git worktree add /tmp/r7check 147c696
cp tests/ml/test_hardening.py /tmp/r7check/tests/ml/test_hardening.py
cd /tmp/r7check && python3 -m pytest tests/ml/test_hardening.py -q \
  -k "market_beta_shifted or sparse_cross_sectional or fold_local_classification"
#  -> expected: 3 failed, each with an AssertionError
cd - && git worktree remove --force /tmp/r7check
python3 -m pytest tests/ml -q -m "not spark and not databricks"   # -> all pass on HEAD
```

Paste both outputs in your verdict. Do not touch anything outside `tests/ml/`.
**Commit your work.** Write `.agents/deepseek/VERDICT-ml-hardening-round7.md`.
