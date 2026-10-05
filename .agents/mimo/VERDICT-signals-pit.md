# VERDICT: signals-pit — MiMo
**Status:** APPROVED
**Round:** 1

## Changes made
- `ml/baseline_labels.py` — new module with:
  - `forward_labels(df, horizon, tol)` — PIT-safe labelling requiring same-day + gap tolerance.
  - `purged_split(lab, frac)` — train/test split using `label_ts <= cut` (no label leakage).
- `scripts/publish_baseline_signals.py` — imports and uses `forward_labels` + `purged_split` instead of the old `shift(-1)` + `prediction_ts <= cut` logic. Module docstring updated to describe the correct label construction.
- `tests/ml/test_baseline_labels.py` — 10 tests covering:
  - 30-min gap same-day → labelled
  - 5-min gap → NaN (overlap)
  - overnight gap → NaN
  - last snapshot → NaN
  - symbols never mix
  - negative return → label 0
  - purged split: no train `label_ts > cut`
  - train/test disjoint
  - mutation tests that FAIL on old `shift(-1)` logic

## Non-blocking notes
- `FutureWarning` on `label_ts` assignment (timezone-aware datetime into NaT column). Harmless; cosmetic fix possible but not blocking.
- Full offline suite (`-m "not spark and not lakebase and not databricks"`) times out on a Databricks-connecting test in `tests/api/`, unrelated to this change.

## Checks run
- `python -m pytest tests/ml/test_baseline_labels.py -v` → 10/10 passed
- `python -m pytest tests/ml/test_pit_no_lookahead.py tests/ml/test_score.py tests/ml/test_evaluate.py -v` → 8/8 passed (existing tests, no regression)
- `python -m pytest tests/ml -q` → 18/18 passed