===VERDICT START===
# VERDICT: strategy-robustness-check2 — DeepSeek
**Status:** CHANGES_REQUESTED
**Round:** 8 (robustness round-2 re-check)

Re-checked commit `0e972e0` (round 2) + round-8 merge (`699093f`) on
`slice/strategy-robustness` at HEAD `5e2920b`. Read-only; scratch under `/tmp`.
Nothing committed or pushed. Working tree clean at end.

## Verdict on the six re-check items

| # | Item | Result |
|---|------|--------|
| 1 | Top-500 is real (full bronze panel) | **PASS** |
| 2 | Parity (dense-grid SQL semantics, missing session) | **PASS** |
| 3 | Drop-top-3 executes, training-window P&L, zero weight | **PARTIAL** — executes + zero-weight PASS; training-window **FAIL** |
| 4 | Report tables (every table, IS/OOS, OOS gate) | **PARTIAL** — headings present; rank IC & capacity & beta/industry **not computed** |
| 5 | Config really consumed (keys + cost params) | **PASS** |
| 6 | Honest trial count (no silent duplicate) | **PASS** |

Round-8 merge did not break the robustness paths: cost-stress charges on the
executed notional (`compute_costs`, `strategies/backtest.py:207-223`), and
`fetch_data` screens the dense-grid panel (`strategies/run_residual_reversion.py:138`).

## Blocking findings

1. **[strategies/robustness.py:737-742; strategies/run_residual_reversion.py:387-398, 517] Rank IC is stubbed and its escape hatch does not exist.**
   `render_robustness_report` emits a "## Rank IC" heading whose only content is
   "_…Run with --rank-ic for full computation._". No `--rank-ic` flag exists in the
   CLI (argparse block at `run_residual_reversion.py:387-398` lists only `--config`,
   `--output`, `--round`, `--book-capital`, `--factor-model`, `--pca-components`,
   `--robustness`, `--robustness-output`). `compute_rank_ic` is imported
   (`run_residual_reversion.py:517`) but never invoked anywhere in the runner or
   report. → Concrete failure: the DeepSeek-must-check item 5 measure ("s-score at t
   vs residual return t+1..t+H, no overlap leakage") has **no observable output**;
   a reader sees a populated-looking report table that was never computed. Round-2
   BUILD §3 required "Call … `compute_rank_ic` for real". The function itself is
   correctly shifted (`robustness.py:378` `shift(-horizon_days)`) — only the wiring
   is missing.

2. **[strategies/robustness.py:722-735; strategies/run_residual_reversion.py:515] Capacity is never computed or printed.**
   The "## Turnover / capacity / margin" table renders only `avg daily turnover` and
   `margin (bps)`; there is no capacity number. `compute_capacity` is imported
   (`run_residual_reversion.py:515`) but never called. → Concrete failure: the
   mandated capacity measure (BUILD change 4; round-2 §3 "call `compute_capacity`
   for real") is absent from the report despite the section heading promising it.

3. **[strategies/robustness.py:705-719] Exposures table never computes beta or industry (sector) exposure.**
   The `compute_exposures` call hardcodes `beta = None` and `industry=None`
   (`robustness.py:707-708`), so the beta rows are `nan` and no industry rows are
   emitted. → Concrete failure: BUILD change 4 requires "exposures (sector, beta,
   dollar)"; only dollar exposure is attempted. Confirmed by rendering a synthetic
   run: the Exposures section prints `max/mean |beta exposure| … nan` and no
   industry lines.

4. **[strategies/robustness.py:200-224; strategies/run_residual_reversion.py:602-611] Drop-top-3 selects contributors from full-period P&L, not the training window.**
   `remove_top_pnl_contributors` computes `pnl_by_sym = (weights.shift(1).fillna(0.0)
   * returns).sum()` over **all** dates, and `_run_variant` feeds it the full-period
   `base_res["net"]` / `base_res["weights"]` / `sig["returns"]` before re-backtesting
   the full period. → Concrete failure: the round-2 BUILD §2 ("compute per-name P&L
   over the **training** window only, then backtest out-of-sample") and this
   check's "uses training-window P&L" are not met; OOS-period P&L feeds back into
   which names are removed. (Note: the original BUILD change 3 described this as a
   "full-period ex-post" stress, so the two specs conflict — but round 2 is the
   operative instruction and it is not implemented.)

## What round 2 fixed (confirmed)

- **Top-500 real (PASS).** `fetch_data` loads the full `bronze_ohlcv_day` panel
  (`run_residual_reversion.py:118-129`) and screens it with
  `screen_universe(panel, n=500)` (`:138`); `_run_variant` re-screens per
  `universe_size` (`:585-589`). `test_top500_differs_from_top300` proves top-500 ⊋
  top-300 on 600 synthetic symbols. No Gold-top-300/current-membership fallback.
- **Parity (PASS).** Dense-grid semantics with a missing session is proven by
  `test_sparse_input_matches_dense_sql_semantics` (`tests/strategies/test_universe.py:180-226`);
  live top-300==gold parity is deferred to Claude (as BUILD round 2 states).
- **Drop-top executes + zero weight (PASS).** `_run_variant` reads `drop_top_pnl`
  (`run_residual_reversion.py:602`), removes top contributors, rebuilds signals on
  the trimmed universe (`:612-622`); `test_drop_top_changes_results` and
  `test_dropped_symbols_tracked` prove the result differs and the dropped names hold
  zero weight. (The training-window defect is finding 4.)
- **Config consumed (PASS).** `min_obs_fraction`, `target_gross`,
  `execution_lag_bars` are read at `run_residual_reversion.py:417-419` and flow
  through `build_signals` → `run_one` → `run_backtest` (`enforce_execution_lag`,
  `neutralize_daily`). `run_one` passes `build_cost_params(cfg)` to `run_backtest`
  in the **baseline** (`:469`, `:421`) — editing `cost_model` now changes the
  baseline, unlike round 7.
- **Honest trial count (PASS).** Registry = 72 unique fingerprints
  (6 baseline + 12 cost + 12 universe + 36 parameter + 6 drop-top), verified
  empirically; every counted variant now changes the computation (no silent
  duplicate). `n_trials=len(registry)` is passed consistently to DSR and printed.
- **Tests pass with pyspark hidden.** See "Checks run" below.

## Answers to the original DeepSeek-must-check list (re-verified)

1. **PCA point-in-time integrity: PASS.** `compute_pca_residuals` fits Ledoit-Wolf +
   eigendecomposition on `train_slice = returns.iloc[t-window:t]` only
   (`residual_reversion.py:303-349`), orients eigenvectors deterministically, and
   applies frozen quantities to day t. `test_pit_loading_integrity` and
   `test_perturb_future_does_not_change_past_outputs` pass.
2. **Universe-size look-ahead: PASS.** (see Top-500 real above).
3. **Trial counting: PASS** (robustness ledger = 72; normal runner still uses
   `n_trials = len(hold_candidates)` for the non-robustness report — unchanged from
   round 7, non-blocking note below).
4. **Cost stress correctness: PASS.** `_scale_params` scales
   commission/spread/slippage/borrow exactly once and leaves
   `adv_participation_cap` untouched (`backtest.py:161-170`); `_run_variant`
   recomputes `net = gross − costs_stress["total"]` once (`run_residual_reversion.py:630-642`).
5. **Other measures: PARTIAL.** Top-3 removal executes (finding 4 caveat); per-fold
   Sharpe via `compute_fold_metrics` present; **rank IC absent** (finding 1).
6. **Config alignment: PASS.** `config.yaml` leads with `residual_reversion` +
   `robustness`; `experimental_strategies` marked `later`/`experimental`;
   `metric_gates` has the five exact gates; `cost_model.adv_participation_cap: 0.01`.
7. **Tests: PASS.** 144 pass with and without pyspark (below).

## Non-blocking notes

- `pca_components` is still not range-validated to [10, 15] (carried from round 7).
- `test_all_config_keys_consumed` (`tests/strategies/test_robustness.py:413-424`) is
  still an existence check, and no consumption test covers the `cost_model` keys
  (round-2 §4 asked for "each cost_model key in turn"); the three added consumption
  tests cover `min_obs_fraction`, `target_gross`, `execution_lag_bars` only.
- In the drop-top branch, `run_one` receives the **untrimmed** `univ_sub` as the
  universe (`run_residual_reversion.py:624`) while signals/returns are trimmed; it is
  harmless today (dropped symbols carry no positions) but should be `univ_trimmed`
  for clarity.
- `_run_variant` re-screens the full panel per variant (72× `screen_universe`) — a
  performance, not correctness, concern.

## Checks run

```
$ python3 -m pytest -q -p no:cacheprovider tests/strategies tests/ml
144 passed, 34 warnings in 77.49s

$ PYTHONPATH=/tmp/ds-nopyspark python3 -m pytest -q -p no:cacheprovider tests/strategies tests/ml
   (sitecustomize.py sets pyspark / pyspark.sql / pyspark.sql.functions / pyspark.sql.types = None)
144 passed, 34 warnings in 73.01s

$ python3 - <<'PY'   # registry + report-content proof
  registry size = 72  (parameter_stress 36, cost_stress 12, universe_stress 12,
                       baseline 6, top_pnl_removal 6)
  RANK IC SECTION: "_Rank IC requires s_score … Run with --rank-ic for full computation._"
  CAPACITY SECTION: '| avg daily turnover | 0.1000 |  | margin (bps) | -1.7 |'   # no capacity
  EXPOSURES SECTION: '… max |beta exposure| | nan | …'                          # beta/industry absent
PY

$ grep -n -- '--rank-ic' strategies/run_residual_reversion.py            # -> no match (flag does not exist)
$ grep -rn 'compute_capacity(\|compute_rank_ic(' strategies/run_residual_reversion.py strategies/robustness.py
    # -> only import/definition lines; never called in the report/runner path
```
===VERDICT END===
