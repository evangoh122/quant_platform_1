# VERDICT: ml-hardening round 5 — MiMo

**Status:** APPROVED
**Round:** 5

## Fixes applied

### 1. `market_beta` look-ahead bias — FIXED

`ml/synthetic_data.py:192`: Added `.shift(1)` within each symbol group before
joining beta to the prediction frame. The return at `t` uses close at `t`, and
bars are stamped at their start, so beta at `t` now uses only information
available before `t`.

### 2. Sparse feature misclassification — FIXED

`ml/features.py:417-469`: `_detect_market_wide_columns` now:
- Only counts timestamps where the feature has `>= min_non_null` (default 2)
  non-null values as qualifying timestamps.
- A column is market-wide only if it is constant on `(almost) all` qualifying
  timestamps (threshold applied to qualifying count, not total count).
- Columns with zero qualifying timestamps are returned in
  `insufficient_coverage` and logged as warnings by the caller.

Return type changed to `Tuple[List[str], List[str]]` — `(market_wide, insufficient)`.

### 3. Fold-local market-wide classification — FIXED

`ml/train.py:255-278`: `run_ablation` now detects market-wide columns from
each fold's training timestamps only, then applies that classification to both
train and validation rows. Neutralization results are cached per unique
market-wide set to avoid redundant computation.

## Files modified

- `ml/synthetic_data.py` — beta shift(1) within symbol
- `ml/features.py` — robust sparse detection + return tuple + caller updated
- `ml/train.py` — fold-local neutralization + new imports
- `tests/ml/test_hardening.py` — 4 new tests for round 5 findings

## Non-blocking notes

- The `_detect_market_wide_columns` and `_filter_numeric_features` functions
  are now imported by `train.py` (underscore-prefixed private helpers). This is
  acceptable for internal cross-module use within the ML lane, but a future
  refactor could expose them as public API if needed.
- The `FutureWarning` about incompatible dtype in neutralisation (line 598) is
  pre-existing and unrelated to this round's changes.

## Checks run

- `python3 -m pytest tests/ml -q -m "not spark and not databricks"` → 37 passed, 17 warnings