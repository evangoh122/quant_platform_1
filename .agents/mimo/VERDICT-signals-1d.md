# VERDICT: signals-1d — MiMo
**Status:** APPROVED
**Round:** 1

## Blocking findings
(none)

## Non-blocking notes
- FutureWarning from pandas on `label_ts` dtype mismatch when assigning tz-aware values to a naive-initialized column. Non-blocking; pandas preserves the value, just warns about future deprecation.
- `daily_close_labels` uses `pd.merge_asof` with `by="symbol"` which requires globally sorted keys (not just per-group). Implementation sorts `prediction_ts` and `close_ts` globally to satisfy this.

## Checks run
- `python -m pytest tests/ml/test_baseline_labels.py -q` → 27 passed (15 existing forward_labels + 12 new daily_close_labels)
- All existing `forward_labels`, `purged_split`, and `refit_rows` tests unchanged and passing.
- 3 named mutation tests included (trade_date vs close_ts, drop max_gap, label from N+1); each will fail if the corresponding guard is removed.
- Integration test: `daily_close_labels → purged_split → refit_rows` on 3-symbol staggered fixture → no train/refit row with label_ts after cutoff.

## Commits
1. `9488d19` feat(ml): add daily_close_labels for 1-trading-day horizon
2. `c38bfd0` feat(scripts): switch publish_baseline_signals to 1d horizon
3. `7b2564a` test(ml): add daily_close_labels tests (1d horizon)