# VERDICT: ml-hardening-round4 — MiMo
**Status:** APPROVED
**Round:** 4

## Blocking findings
(none)

## Non-blocking notes
- `_detect_market_wide_columns` uses a 90% threshold (`n_constant/n_ts >= 0.9`) for detecting market-wide columns. This is conservative enough for real data where a single missing value wouldn't break detection, but could be tuned if needed.
- The FutureWarning about bool dtype on `sec_material_event` (line 571) is pre-existing from round 3 — residualising a bool column produces floats. Not in scope for this round.
- `_filter_numeric_features` attempts `pd.to_numeric` coercion before rejecting a column, so columns with mixed numeric/string values where at least some are numeric will still be residualised.

## Checks run
- `python3 -m pytest tests/ml -q -m "not spark and not databricks"` → 33 passed, 17 warnings (all pass)
- `python3 -m ml.run_ablation --n-symbols 18 --n-bars 100 --seed 42` (with INFO logging) → arm D log confirms:
  ```
  neutralisation: excluded non-numeric/timestamp columns: ['cot_regime_label']
  neutralisation: excluded market-wide columns (passed through unchanged): ['cot_lev_money_zscore', 'cot_crowding_score']
  ```
- COT features `cot_lev_money_zscore` and `cot_crowding_score` now pass through neutralisation unchanged; arm D's COT columns differ from arm C's.

## Files changed
- `ml/features.py` — `_detect_market_wide_columns`, `_filter_numeric_features`, updated `neutralize_features` signature and logic
- `tests/ml/test_hardening.py` — 5 new tests for market-wide detection, override, non-numeric exclusion, COT survival, arm D-vs-C differentiation