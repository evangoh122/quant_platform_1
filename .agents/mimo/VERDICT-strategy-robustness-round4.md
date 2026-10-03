# VERDICT: strategy-robustness-round4 — MiMo
**Status:** APPROVED
**Round:** 4

## Blocking findings
- None. All four blocking findings from DeepSeek check3 are resolved.

## Fixes applied

1. **Residual IC target** (`strategies/run_residual_reversion.py:251`, `:725`):
   `build_signals` now returns `res["residual"]` (OLS and PCA) under the key
   `"residual"`. `_run_variant` stores `sig.get("residual")` as
   `residual_returns`, not `sig.get("returns")` (raw total returns). Rank IC
   now correctly correlates s-score[t] against forward H-day cumulative
   **residual** return.

2. **Newey-West HAC t-stat** (`strategies/robustness.py:367-435`):
   `compute_rank_ic` uses a Newey-West (HAC) standard error with
   Bartlett kernel and lag = H-1. Also reports `effective_n = n // H`
   (non-overlapping count). On an AR(1)-correlated synthetic IC series
   the HAC t-stat is ~40-50% lower than the naive `mean/(std/sqrt(n))`,
   consistent with the expected `1/sqrt(H)` reduction at H=5.

3. **Drop-top-3 like-for-like** (`strategies/run_residual_reversion.py:560-629`):
   Per-fold drop-top-3 now runs the actual backtest (costs, neutralisation,
   ADV cap) on the trimmed universe (top-3 excluded from eligible set) to
   produce a NET comparison. Both "OOS Sharpe (full)" and "OOS Sharpe (drop3)"
   are now NET. With zero costs both agree with hand computation; with nonzero
   costs drop-3 is charged costs.

4. **Sector exposure** (`strategies/robustness.py:254-310`):
   `compute_exposures` reports `max |sector net exposure|` per sector and the
   overall `max_abs_sector_exposure`. The report renders these as
   `max |sector net| (sector_name)` rows. No more mean signed net.

## Non-blocking notes
- `compute_exposures` API changed: now returns `max_abs_sector_exposure` key.
  Existing callers (report, tests) updated; no external consumers found.
- The `effective_n` field is new in `compute_rank_ic` return dict.

## Checks run

```
$ python3 -m pytest -q -p no:cacheprovider tests/strategies tests/ml
158 passed, 34 warnings in 106.43s

$ PYTHONPATH=/tmp/nopyspark python3 -m pytest -q -p no:cacheprovider tests/strategies tests/ml
158 passed, 34 warnings in 105.78s

$ python3 -m pytest -q -p no:cacheprovider tests/strategies/test_robustness_round4.py
8 passed in 6.21s

$ python3 -m pytest -q -p no:cacheprovider tests/strategies/test_robustness_round3.py
6 passed in 4.86s

# Guard test: 8 round-4 tests FAIL on pre-fix HEAD (prove residual is wrong,
# t-stat is naive, drop-3 is gross-vs-net, sector exposure is mean signed).

# LF line endings verified: no CRLF in any modified file.
# No secrets committed. No changes to .agents/dispatch.sh or strategies/results/.
```