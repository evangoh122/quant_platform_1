# BUILD: strategy robustness lane

MiMo owns implementation. Work on `slice/strategy-robustness`, which is based on
`slice/strategy-residual-reversion` / PR #16. Preserve the existing causal execution,
universe, neutralisation, and cost behavior. The latest live baseline is
`strategies/results/residual_reversion_r5.md` (net Sharpe -0.363, OOS Sharpe -0.623,
DSR 0.000); do not describe this or any new result as evidence of edge.

Constraints: MiMo runs on Windows without Databricks. All calculation and rendering
logic must be pure pandas/numpy/scikit-learn and testable with synthetic frames;
Databricks imports and calls belong behind the live-run boundary. Use LF endings. Do
not touch `.agents/dispatch.sh`. Commit the implementation and write
`.agents/mimo/VERDICT-strategy-robustness.md` with changed files, tests, the old-code
failure proof, and commit SHA.

## Current-code facts that govern the design

- `strategies/config.yaml:23-86` still presents unbuilt pairs/alpha/ML strategies as
  the numbered strategies, while the built residual strategy is absent. It also says
  2% ADV at line 21 although `strategies/cost_model.py:15-31` defaults to 1%.
- The runner hardcodes factor/strategy settings at
  `strategies/run_residual_reversion.py:265-294`; `build_signals` at lines 132-177
  supports only market/industry OLS. The existing three `max_hold` candidates at
  lines 286-294 are genuine tried configurations and must be included in the trial
  accounting if retained.
- `compute_residuals` at `strategies/residual_reversion.py:174-239` is correctly
  lagged for OLS betas; preserve it as the `ols_mkt_ind` implementation.
- `run_backtest` at `strategies/backtest.py:290-358` currently exposes only 1x and
  2x costs. `compute_costs` at lines 168-222 already takes a multiplier and must be
  the sole source of cost stress (including commission, spread, slippage, and borrow).
- `gold/06_gold_tradable_universe.sql:31,129` persists only the top 300. Therefore
  top-500 cannot be obtained by filtering that Gold table. Its exact PIT screen is at
  lines 36-130: dense market calendar, 60 complete prior sessions, 252 prior valid
  observations, all five prior market sessions present, rank by lagged median ADV.
- `strategies/universe.py:15-65` is the offline reference, but its input must be a
  dense market-calendar panel to match SQL recency semantics.
- Scikit-learn is already used lazily in `ml/train.py:125-129`; use
  `sklearn.covariance.LedoitWolf`. Do not add another numerical dependency.
- Reuse `ml.train.purged_walk_forward_splits` (`ml/train.py:68-120`),
  `ml.evaluate.daily_rank_ic` (`ml/evaluate.py:62-92`), and
  `ml.evaluate.deflated_sharpe_ratio` (`ml/evaluate.py:95-116`).

## Numbered changes

1. **Make residual mean-reversion the primary configured strategy.** Replace the
   misleading strategy section at `strategies/config.yaml:23-103` with a
   `residual_reversion` block consumed by the runner. Use these exact keys (and no
   decorative/dead keys): `status: primary`, `bar_freq: 1d`,
   `factor_model: ols_mkt_ind`, `factor_window: 60`, `pca_components: 10`,
   `residual_lookback: 5`, `entry_threshold: 2.5`, `exit_threshold: 0.5`,
   `max_hold_candidates: [3, 5, 10]`, `min_obs_fraction: 0.8`,
   `universe_size: 300`, `target_gross: 1.0`, `book_capital: 10000000`, and
   `execution_lag_bars: 1`. Align `cost_model.adv_participation_cap` to `0.01` and
   add its existing borrow assumptions (`borrow_bps_daily` and
   `borrow_bucket_thresholds`) so `CostParams` is built from config rather than
   defaults. Keep `metric_gates`, but ensure it contains the exact requested gates:
   `sharpe_min: 1.25`, `max_drawdown_max: 0.15`, `return_to_dd_min: 1.0`,
   `margin_min_bps: 5.0`, `oos_ratio_min: 0.50`. Put robustness settings in a
   runner-consumed `robustness` block: `cost_multipliers: [1.0, 2.0, 3.0]`,
   `universe_sizes: [200, 300, 500]`, `parameter_perturbation: 0.20`,
   `drop_top_pnl_contributors: 3`, `walk_forward_folds: 5`,
   `min_profitable_folds: 3`, and `rank_ic_horizon_days: 5`.

   Retain intraday pairs and daily alpha basket only under a clearly named
   `experimental_strategies` mapping with `status: later` / `status: experimental`;
   do not let those blocks enter this runner or the trial count. Remove the stale
   Strategy 3 inheritance claim. Update `docs/QUANT_STRATEGIES.md:1-75` status and
   build-order wording to say residual **mean-reversion** is primary and built,
   OLS market/industry is the baseline, PCA is the statistical-factor variant, and
   pairs/daily alpha are later/experimental. Preserve the industry-taxonomy caveat.

   Add `load_strategy_config(path: str | Path) -> dict`,
   `build_cost_params(config: Mapping) -> CostParams`, and
   `validate_residual_config(config: Mapping) -> None` in
   `strategies/run_residual_reversion.py` near lines 37-43. The validator must reject
   unknown residual keys and missing keys. `main()` must obtain every residual-block
   value through this mapping; no duplicated strategy literal may remain. Add
   `--config PATH` (default `strategies/config.yaml`). A test must spy on/inject the
   runner call path and assert every key in `residual_reversion` is read and affects
   the corresponding call/metadata; unknown keys must raise. Parsing alone is not
   consumption.

2. **Add a causal PCA residual factor model.** Extend
   `strategies/residual_reversion.py` after `compute_residuals` with exact public API:

   ```python
   compute_pca_residuals(
       returns: pd.DataFrame,
       window: int = 60,
       lookback: int = 5,
       n_components: int = 10,
       min_obs: int | None = None,
   ) -> dict[str, pd.DataFrame]
   ```

   For each date `t`, fit `sklearn.covariance.LedoitWolf` and the eigendecomposition
   using only rows `[t-window, t-1]` and only symbols eligible/finite in that training
   slice. Standardize using means/scales from that lagged slice, order eigenvectors by
   descending eigenvalue, retain `min(n_components, rank, available symbols)` with a
   validated configured K in [10, 15], and orient eigenvectors deterministically
   (largest-absolute loading positive) so tests are stable. Estimate each stock's
   intercept/loadings on the lagged factor scores; apply those frozen quantities to
   day `t` to produce its residual. Do not fit/transform on day `t`, do not impute
   day-t values into training, and return `residual`, `sigma`, `s_score`, plus
   inspectable lagged `loadings` (date × symbol × component; a documented long frame
   is acceptable) and factor diagnostics. Use the same trailing residual volatility,
   s-score definition, `generate_signals`, execution lag, neutralisation, and
   `run_backtest` as OLS.

   Extend `build_signals(...)` at `strategies/run_residual_reversion.py:132` with exact
   parameters `factor_model: str` and `pca_components: int`, dispatch only
   `ols_mkt_ind` or `pca`, and return the common keys used downstream. Add CLI
   overrides `--factor-model {ols_mkt_ind,pca}` and `--pca-components K`; overrides
   must be applied to a fresh config copy, never mutate module/global state.

   Synthetic tests in `tests/strategies/test_pca_residual_reversion.py` must cover:
   correct shapes and common signal/backtest path; invalid K; deterministic output;
   and the primary PIT proof: change one or all returns on day `t` and assert the
   complete loading matrix used at `t` is exactly unchanged (while day-t residuals
   may change). Also perturb all dates after `t` and prove all outputs through `t`
   remain unchanged. Tests must fail against the pre-change checkout.

3. **Build the pure robustness library.** Create `strategies/robustness.py` with these
   exact public names and typed, documented inputs/outputs:

   - `VariantSpec` (frozen dataclass) and
     `build_variant_registry(base_config: Mapping) -> list[VariantSpec]`;
   - `run_cost_stress(...)`, `run_universe_stress(...)`,
     `run_parameter_stress(...)`, `remove_top_pnl_contributors(...)`;
   - `compute_fold_metrics(net_returns, splits)`,
     `compute_exposures(weights, beta, industry)`,
     `compute_capacity(weights, adv, book_capital, participation_cap)`,
     `compute_margin_bps(net_returns, turnover)`, and
     `compute_rank_ic(s_score, residual_returns, horizon_days)`;
   - `evaluate_gates(metrics: Mapping, gates: Mapping) -> dict[str, str]` returning
     only `PASS`, `FAIL`, or `N/A` per gate; and
     `render_robustness_report(...) -> str`.

   `build_variant_registry` is the single ledger for multiple testing. Give every
   unique tried parameter vector a stable ID and fingerprint; deduplicate the nominal
   1x/top-300/unperturbed baseline rather than counting it repeatedly. Register both
   factor models, all max-hold candidates actually compared, cost 1x/2x/3x,
   top-200/top-300/top-500, and one-at-a-time -20%/+20% changes to each of
   `entry_threshold`, `exit_threshold`, and `factor_window`, plus the top-3-removal
   run. Integer windows use deterministic rounding and remain positive. The DSR
   `n_trials` is `len(registry)` (all OLS and PCA unique configurations, including
   losing/failed/NaN runs), never the number of winners, report rows, or folds. If a
   CLI selection executes only a subset, the report must say `executed trials` and
   use that exact count; the full `--robustness` run must execute the full registry.

   Cost stress must rerun `run_backtest` with the same weights/signals and pass the
   requested multiplier through `compute_costs`; at 2x/3x every bps component,
   including borrow, scales exactly once, while ADV participation and gross P&L do
   not change. Do not subtract the already-net series again.

   Universe stress must build independent daily PIT membership for 200/300/500 before
   signal calculation. For the live path, change `fetch_data` near
   `strategies/run_residual_reversion.py:68-98` to fetch the full required daily
   `symbol,event_date,close,volume` panel from `bronze_ohlcv_day` (plus SPY/RSP/QQQ),
   then call a dense-calendar-correct `screen_universe(..., n=500)` once and slice by
   `adv_rank <= N`. Do **not** source 500 from `gold_tradable_universe`, union present
   constituents across dates, use current membership historically, or rank same-day
   volume. The pandas result for ranks <=300 must have a parity test against a
   synthetic SQL-semantics fixture, including a missing-session symbol.

   Removing top contributors means compute each symbol's total realized **net** P&L
   contribution using executed/lagged, capacity-capped weights and allocated costs,
   identify the three largest contributors without future information being fed back
   into the original strategy, then report a clearly labelled full-period ex-post
   concentration stress with those symbols zeroed and the portfolio/costs recomputed.
   It is not an investable PIT variant; it still counts as a tested variant.

   Fold metrics use the same five purged/embargoed walk-forward validation folds as
   the strategy selection, report each fold's net Sharpe and net annualized return,
   and set `profitable_3_of_5 = PASS` only when at least three validation folds have
   total net P&L > 0. Exposure output is daily and summarized with max absolute and
   mean absolute dollar exposure (`sum(weights)` / gross), beta exposure
   (`sum(weights*beta)` / gross), and each industry exposure. Call it repo-taxonomy
   industry exposure, not GICS sector exposure.

   Capacity is the maximum deployable capital implied by each nonzero executed order
   (`participation_cap * ADV / abs(delta_weight_open_leg)`), summarized conservatively
   by the minimum finite constraint (and optionally percentiles); do not repeat the
   current sum-of-ADV budget at `run_residual_reversion.py:126-129`. Margin bps is
   `sum(net_return) / sum(one_way_turnover) * 10_000`, `N/A` when denominator is zero.
   Rank IC is the per-date Spearman rank correlation between `s_score[t]` and the
   next-H-day cumulative **residual** return with sign clearly stated (raw s-score
   should predict negative future residual return under mean reversion); shift the
   target so no future value enters the signal, and report mean/std/t-stat/N.

4. **Wire runner flags and report.** Add exact flags to
   `strategies/run_residual_reversion.py:265-276`: `--robustness` (full suite),
   `--robustness-output PATH` (default
   `strategies/results/robustness_r1.md`), `--factor-model`, `--pca-components`, and
   `--config`, while preserving `--output`, `--round`, and `--book-capital` backwards
   compatibility. `--robustness` writes the new report; a normal invocation may keep
   writing the residual round report. The full report must have a methodology/config
   section and a separate Markdown table for: factor-model comparison, cost stress,
   universe stress, threshold/window perturbations, top-3 contributor removal, five
   walk-forward folds, exposures, turnover/capacity/margin, and rank IC.

   Every variant row must show net Sharpe, absolute max drawdown, return/drawdown,
   margin bps, IS Sharpe, OOS Sharpe, OOS/IS ratio, DSR, trial count, and separate
   PASS/FAIL/N/A columns for the five configured gates. Define maxDD gate using
   `abs(max_drawdown) <= 0.15`; return/DD uses annualized net return divided by
   `abs(max_drawdown)`; OOS-ratio gate is `OOS Sharpe >= 0.5 * IS Sharpe` only where
   the ratio is meaningful, otherwise `N/A` with the raw values visible. Include the
   literal statement: “PASS/FAIL denotes configured research gates, not evidence or
   a claim of edge.” State the true total executed trial count prominently and pass
   the same count to every reported DSR. Never silently omit failed/NaN variants.

5. **Tests and isolation.** Add focused tests under `tests/strategies/` for config
   consumption/rejection, PCA PIT invariants, variant registry/deduplication and trial
   count, cost scaling exactly once, PIT 200/300/500 membership, parameter values,
   top-contributor removal, five-fold profitability flag, exposures, capacity,
   margin, forward residual rank IC alignment, gate boundary behavior, report tables,
   and CLI parsing. Synthetic data only; no credentials, network, Spark, or ambient
   environment variables. Each test must create fresh inputs/config and must prove no
   module/global state leaks across tests or repeated runner calls.

   Add a subprocess acceptance test using a temporary `sitecustomize.py` containing:

   ```python
   import sys
   for m in ("pyspark", "pyspark.sql", "pyspark.sql.functions", "pyspark.sql.types"):
       sys.modules[m] = None
   ```

   It must import `strategies.residual_reversion`, `strategies.robustness`,
   `strategies.universe`, `strategies.backtest`, and the runner helpers and execute a
   small synthetic OLS/PCA robustness run. Do not rely on test collection order.

6. **Prove tests are new and commit.** Before implementation, copy the current tree
   to a disposable `/tmp` directory (excluding `.git` is fine), add only the new tests
   there, and run the focused commands. Record test names and failure excerpts showing
   every new test fails against current code for the intended missing behavior (an
   import/collection failure alone is insufficient for all behavioral tests; stage
   minimal test imports if needed). Then implement, run all acceptance commands, keep
   LF line endings, do not touch `.agents/dispatch.sh`, commit, and write the required
   MiMo verdict.

## Acceptance commands

Run from repository root on MiMo's Windows environment (use the environment's Python
launcher consistently):

```bash
python -m pytest -q tests/strategies
python -m pytest -q tests/ml/test_walk_forward.py tests/ml/test_hardening.py
python -m pytest -q
python -m compileall -q strategies ml
python -c "from pathlib import Path; bad=[str(p) for p in Path('.').rglob('*') if p.is_file() and (p.suffix in {'.py','.yaml','.md'} or p.name.endswith('.sql')) and b'\r\n' in p.read_bytes()]; assert not bad, bad"
git diff --check
git status --short
```

Also run the focused new suite against the `/tmp` pre-change copy and include the
expected-failure evidence in `.agents/mimo/VERDICT-strategy-robustness.md`. The final
`git status --short` must be clean after committing except coordinator-owned files,
if any, that predated the work.

## Live command for Claude (WSL, after DeepSeek approval)

```bash
python strategies/run_residual_reversion.py --config strategies/config.yaml --robustness --robustness-output strategies/results/robustness_r1.md --output strategies/results/residual_reversion_r6.md --round 6
```

The command must query Databricks only in `fetch_data`; all resulting frames then run
through the same tested pure functions. It must fetch the full Bronze daily panel so
top-500 is actually available and PIT-derived, not silently fall back to top-300.

## DeepSeek must check

DeepSeek must return `APPROVED` or `CHANGES_REQUESTED` with file:line evidence in
`.agents/deepseek/VERDICT-strategy-robustness.md`, explicitly checking:

1. PCA point-in-time integrity: day-t/future perturbations cannot alter loadings used
   at t, and shrinkage/fitting use only `[t-window, t-1]`.
2. Universe-size integrity: top-500 comes from the full Bronze panel with the SQL's
   lagged dense-calendar rules; no Gold-top-300/current-membership look-ahead.
3. Trial counting: one unique registry, nominal deduplication, every actually tried
   OLS/PCA/hold/cost/universe/parameter/drop variant counted, identical true count
   supplied to DSR and printed in the report.
4. Cost stress correctness: commission/spread/slippage/borrow scale exactly once;
   participation limits and gross P&L do not scale; no double subtraction of costs.
5. Config has no dead residual keys, runner overrides do not leak state, report gates
   use correct signs/denominators, and all tests work with pyspark hidden.
