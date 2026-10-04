# VERDICT: strategy-residual-reversion-round12 — MiMo
**Status:** APPROVED
**Round:** 12

## Blocking findings
- None

## Non-blocking notes
- The mutation test verifies the mask is load-bearing by checking NaN/finite status of returns (not by triggering a signal), because the s-score mechanism is robust to single outlier returns — the trailing sigma inflates proportionally. The core invariant (masked day → NaN return) is directly tested.
- `fetch_masked_breaks` queries `data_quality_breaks` where `is_masked = true`. If the table is empty or unavailable at runtime, the function returns an empty set (no masking applied). This is safe but should be monitored.
- The `--price-table` CLI default is `silver_ohlcv_day_adjusted`; falling back to `bronze_ohlcv_day` emits a `warnings.warn()` at fetch time. The warning is visible in stderr but not in the results report — the report header shows the source table name.

## Checks run
- `python -m pytest -q tests/strategies` → 57 passed (0 failed)
- `python -m pytest -q tests/ml` → 37 passed (0 failed)
- `git diff --stat` → 7 files changed, 284 insertions, 11 deletions