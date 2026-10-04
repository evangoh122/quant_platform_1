# VERDICT: strategy-round8 — MiMo
**Status:** APPROVED
**Round:** 8

## Blocking findings
None — all four Codex findings fixed.

## Fixes applied

### 1. `strategies/backtest.py:~206-216` — exit/reduction costs undercharged
**Root cause:** `compute_costs` called `scale_order_to_adv_cap` on the executed notional, capping costs at 1% of ADV even for large exits that `cap_weight_changes_by_adv` already allowed through.
**Fix:** Removed the re-cap. Costs now charge on the full executed notional `|dw| * book_capital` with true participation `(notional / ADV)` for the slippage term, uncapped.

### 2. `strategies/universe.py:36-48` — pandas didn't match SQL dense-grid semantics
**Root cause:** `screen_universe` rolled only over rows present per symbol. SQL builds a dense symbol × market-date grid so missing sessions are NULL rows inside the window.
**Fix:** Reindex each symbol onto the full market calendar (`all_dates = sorted(panel["event_date"].unique())`) via `pivot` + `reindex` + `melt` before the `groupby` + `rolling`. Missing sessions are now NaN rows in the rolling window.

### 3. `gold/07_gold_regime_features.sql:89` — partial z-score window
**Root cause:** Guard used `COUNT(*)` which counts all rows including NULL `rsp_spy_ratio`, but `AVG`/`STDDEV` ignore NULLs. A 252-row window with missing SPY/RSP observations produced a partial-window z-score.
**Fix:** Changed `COUNT(*)` to `COUNT(rsp_spy_ratio)` in the 252-row window guard.

### 4. `strategies/run_residual_reversion.py:394` — leverage wording
**Root cause:** Said "100% long / 100% short" for gross=1.0. With `sum|w| = 1` and dollar neutrality, it's 50%/50%.
**Fix:** Changed to "50% long / 50% short".

## Tests that FAIL on HEAD and PASS with fixes

```
$ git stash  # revert to HEAD
$ python3 -m pytest -q tests/strategies/test_backtest.py::test_exit_costs_charged_on_full_executed_notional tests/strategies/test_backtest.py::test_costs_never_below_minimum_bps_times_executed_notional tests/strategies/test_universe.py::test_sparse_input_matches_dense_sql_semantics tests/strategies/test_universe.py::test_gold_07_zscore_guard_counts_column_not_star tests/strategies/test_run_residual_reversion.py::test_leverage_wording_says_50pct
FAILED test_exit_costs_charged_on_full_executed_notional — expected 0.005100, got 0.000004
FAILED test_costs_never_below_minimum_bps_times_executed_notional — entry cost 0.00004000 < minimum 0.00010000
FAILED test_sparse_input_matches_dense_sql_semantics — S00 admitted on dates 31-35 despite missing session
FAILED test_gold_07_zscore_guard_counts_column_not_star — guard uses COUNT(*) not COUNT(rsp_spy_ratio)
FAILED test_leverage_wording_says_50pct — says '100% long / 100% short'
5 failed

$ git stash pop  # restore fixes
$ python3 -m pytest -q tests/strategies tests/ml
83 passed, 34 warnings
```

## Checks run
- `python3 -m pytest -q tests/strategies tests/ml` → 83 passed, 34 warnings
- `PYTHONPATH=/tmp/nopyspark python3 -m pytest -q tests/strategies tests/ml` → 83 passed, 34 warnings
- HEAD regression (5 new tests) → 5 failed (proves tests are meaningful)
- Fix regression (5 new tests) → 5 passed
- LF line endings verified (`file` command, no CRLF)
- No secrets committed
- No changes to `.agents/dispatch.sh` or `strategies/results/`