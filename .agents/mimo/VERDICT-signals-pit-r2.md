# VERDICT: signals-pit-r2 — MiMo
**Status:** APPROVED
**Round:** 2

## Blocking findings
- None. All DeepSeek CHANGES_REQUESTED items resolved.

## Non-blocking notes
- FutureWarning (N5 from DeepSeek r1): `label_ts` writes tz-aware into naive NaT column at `ml/baseline_labels.py:82`. Will raise in a future pandas. Not addressed in this round (out of scope).
- `import random` inside test function `test_forward_labels_handles_shuffled_input` — acceptable for test code but could be a module-level import.

## Checks run
- `python3 -m pytest tests/ml -q` → **50 passed** (130s)
- mutation *drop same-day check* (`valid = ok_gap & nxt_ret.notna()`) on `test_midnight_straddle_is_nan` → **FAILED** (AssertionError: `Midnight-straddle row must be NaN (different US/Eastern dates)`) — F1 resolved

## Items addressed

### F1 (blocking): midnight-straddle mutation test
Added `test_midnight_straddle_is_nan` — two snapshots exactly 30 min apart (23:45 ET / 00:15 ET, given as UTC 03:45 / 04:15) that straddle midnight US/Eastern. Asserts NaN. Mutation test (removing `same_day` from `valid`) → **FAILED** as required.

### N1: removed inline buggy re-implementations
Deleted `_forward_labels_plain_shift`, `test_plain_shift_labels_5min_gap`, `_purged_split_on_prediction_ts`, and `test_prediction_ts_split_leaks_label`. The real shipped-code mutation coverage comes from `test_5min_gap_is_nan`, `test_overnight_gap_is_nan`, `test_purged_split_no_label_leak` (verified in DeepSeek r1 mutation matrix).

### N3: forward_labels sorts internally
`forward_labels` now sorts by `[symbol, prediction_ts]` (stable sort) before grouping. Docstring updated. `test_forward_labels_handles_shuffled_input` verifies shuffled input produces identical labels.

### N2: duplicate prediction_ts
`test_duplicate_prediction_ts_earlier_gets_nan` — duplicate timestamp yields gap=0 < tol → earlier row NaN, later row labels correctly. No crash.

### N4: tz-naive input
`test_tz_naive_input_treated_as_utc` — tz-naive timestamps are localized as UTC by `_eastern_date`, labels work correctly.