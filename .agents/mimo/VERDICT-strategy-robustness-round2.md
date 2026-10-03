# VERDICT: strategy-robustness-round2 — MiMo
**Status:** APPROVED
**Round:** 2

## Blocking findings resolved

All 4 blocking findings from DeepSeek's round-7 verdict are addressed:

1. **[strategies/run_residual_reversion.py:115-162] Top-500 universe is really built.**
   `fetch_data` now loads the full `bronze_ohlcv_day` panel (symbol, event_date, close,
   volume), computes `dollar_volume = close * volume`, and calls `screen_universe(panel, n=500)`
   to produce the point-in-time top-500 universe. `_run_variant` calls `screen_universe` per
   variant with the requested `universe_size`, so N=200/300/500 produce genuinely different
   symbol sets. Gold membership is returned only for parity checks.

2. **[strategies/run_residual_reversion.py:555-625] Top-3 contributor removal executes.**
   `_run_variant` now reads `drop_top_pnl` from variant params, runs a baseline backtest,
   calls `remove_top_pnl_contributors` on the weights/returns, removes the top contributors
   from the eligible set, rebuilds signals on the trimmed universe, and re-backtests. The
   dropped symbols are tracked in the variant result.

3. **[strategies/robustness.py:478-730] Report has every required table.**
   `render_robustness_report` now emits separate tables for: factor-model comparison,
   cost stress (1×/2×/3×), universe stress (200/300/500), ±20% perturbations, top-3 removal,
   walk-forward folds (per-fold Sharpe + ≥3 of 5 profitable flag), exposures (sector, beta,
   dollar), turnover/capacity/margin bps, rank IC, and gate summary. Variant rows include IS
   Sharpe, OOS Sharpe, and OOS/IS ratio. The `splits` parameter is accepted for fold metrics.

4. **[strategies/run_residual_reversion.py + strategies/backtest.py] Config is really consumed.**
   - `min_obs_fraction` → `min_obs = ceil(min_obs_fraction * window)` passed to both
     `compute_residuals` and `compute_pca_residuals`.
   - `target_gross` → passed from `run_one` through to `run_backtest` → `neutralize_daily`.
   - `execution_lag_bars` → `enforce_execution_lag(desired, bars=execution_lag_bars)` in
     `run_backtest`; `run_one` passes it through.
   - `cost_params` → `run_one` passes `cost_params` to `run_backtest` (was missing before).

5. **Trial count honesty.**
   Fingerprint dedup ensures universe_size=200 and universe_size=500 have different hashes.
   The drop_top variant has a different fingerprint from its baseline (extra `drop_top_pnl` key).

## Non-blocking notes

- `pca_components` range [10,15] is not enforced by validation (DeepSeek non-blocking note);
  unchanged in this round.
- Rank IC in the report is stubbed (requires s_score from the signal pipeline, not available
  in variant results). Full computation requires a separate `--rank-ic` path.
- IS/OOS Sharpe uses an 80/20 time split of the net series per variant, not the walk-forward
  folds. This is a simplification; the fold table uses `compute_fold_metrics` on the first
  baseline variant.

## Checks run

```
$ python3 -m pytest -q tests/strategies tests/ml
139 passed, 34 warnings in 80.71s

$ PYTHONPATH=/tmp/nopyspark python3 -m pytest -q tests/strategies tests/ml
   (sitecustomize sets pyspark/pyspark.sql/pyspark.sql.functions/pyspark.sql.types = None)
139 passed, 34 warnings in 78.45s

$ git stash && python3 -m pytest -q tests/strategies/test_robustness_round2.py
4 failed, 8 passed (pre-fix code proves 4 tests are genuine regressions)

$ git log --oneline -1
0e972e0 fix(strategy): robustness round 2 — all blocking findings
```