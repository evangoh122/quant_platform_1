# BUILD: strategy robustness round 2 (MiMo)

DeepSeek returned CHANGES_REQUESTED (`.agents/deepseek/VERDICT-strategy-robustness.md`). Read it in full.
Round 1 registered and counted several stresses that **never actually run**. That is the worst kind of
defect for a research report: it overstates rigor. Every variant counted in `n_trials` must change
the computation, and a test must prove it.

## 1. Top-500 universe is really built (blocking #1)
- `fetch_data` must load a full point-in-time daily panel from `bronze_ohlcv_day`
  (`symbol, event_date, close, volume`), plus SPY/RSP/QQQ. Do not restrict it to gold members.
- Call `strategies.universe.screen_universe(panel, n=500)` once, then slice `adv_rank <= N` for
  N in {200, 300, 500}.
- Keep `gold_tradable_universe` only for a **parity check**: top-300 from the pandas screen must
  equal the gold membership. Claude checks that live.
- Unit tests:
  - a synthetic parity test vs a hand-built SQL-semantics expectation, including a symbol with a
    missing session (dense-grid semantics; coordinate with round 8 of `strategies/universe.py`);
  - a test that top-500 ≠ top-300 on synthetic data with 600 symbols.

## 2. Top-3 contributor removal executes (blocking #2)
`_run_variant` must apply `drop_top_pnl`. Compute the per-name P&L over the **training** window only,
remove the top-3 names from the eligible set, then backtest out-of-sample.
Test: the drop-top variant's result differs from the baseline on synthetic data where 3 names carry
the P&L, and the dropped names hold zero weight.

## 3. The report has every required table (blocking #3)
`render_robustness_report` emits separate tables for:
- the factor-model comparison;
- cost stress 1×/2×/3×;
- universe 200/300/500;
- the ±20% perturbations;
- top-3 removal;
- the five walk-forward folds (per-fold Sharpe, plus a "≥3 of 5 profitable" flag);
- exposures (sector, beta, dollar);
- turnover / capacity / margin bps;
- rank IC.

Variant rows include IS Sharpe, OOS Sharpe and the OOS/IS ratio, so the `oos_ratio_min` gate is
evaluated, not N/A. Call `compute_fold_metrics`, `compute_exposures`, `compute_capacity` and
`compute_rank_ic` for real.
Test: render from a synthetic run and assert every table heading and the gate columns are present
and non-empty.

## 4. Config is really consumed (blocking #4)
- Wire `min_obs_fraction`, `target_gross` and `execution_lag_bars` through to `residual_reversion`
  (both OLS and PCA) and to `backtest` (lag).
- `run_one` passes `build_cost_params(cfg)` to `run_backtest`.
- Replace the existence-only test with a **consumption** test: change each residual config key and
  each `cost_model` key in turn, and assert that the runner's call path receives the changed value.
  Spy on it or check the output changes.

## 5. Trial count is honest
`n_trials` counts only variants that ran and produced distinct results. Add a test that fails if two
counted variants give identical results without the identity being intended.

Run:
- `python3 -m pytest -q tests/strategies tests/ml`;
- `PYTHONPATH=/tmp/nopyspark python3 -m pytest -q tests/strategies`, with a sitecustomize that sets
  `sys.modules[m]=None` for pyspark, pyspark.sql, pyspark.sql.functions and pyspark.sql.types.

Every new test must fail on the current HEAD (prove it in /tmp). LF line endings only. Don't touch
`.agents/dispatch.sh` or `strategies/results/`. Commit. Write
`.agents/mimo/VERDICT-strategy-robustness-round2.md`.

Note: strategy round 8 on the `#16` branch also edits `universe.py`, `backtest.py` and
`gold/07`. Claude will merge it in afterwards. Keep your edits to those files minimal and
interface-stable.
