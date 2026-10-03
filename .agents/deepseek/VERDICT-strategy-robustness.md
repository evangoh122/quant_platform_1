===VERDICT START===
# VERDICT: strategy-robustness + PCA lane — DeepSeek
**Status:** CHANGES_REQUESTED
**Round:** 7

Checked commit `9df2030` (implementation) + round-7 merge on `slice/strategy-robustness`.
Read-only; all scratch under `/tmp`. Nothing committed or pushed.

## Blocking findings

1. **[strategies/run_residual_reversion.py:116-119, 125-133, 520] Universe-size integrity: top-500 silently degrades to top-300.**
   `fetch_data` reads membership from `gold_tradable_universe` only — a table that
   persists the top-300 (`gold/06_gold_tradable_universe.sql:31` `universe_n INT DEFAULT 300`,
   `:129` `WHERE r.adv_rank <= universe_n`). The closes query (`:125-133`) is restricted to
   gold constituents plus SPY/RSP/QQQ and fetches no `volume`, so there is no full
   Bronze daily panel to re-screen from. `_run_variant` (`:520`) then slices
   `universe[universe["adv_rank"] <= universe_size]`; for `universe_size == 500` this
   returns only the ≤300 persisted rows, so the top-500 universe-stress variant is
   numerically identical to top-300 while being reported and counted as a distinct
   trial. `screen_universe` (`strategies/universe.py:15`) is never invoked by the runner,
   and there is no parity test of ranks ≤300 against SQL semantics (BUILD change 3
   explicitly requires one, including a missing-session symbol). This defeats
   DeepSeek-must-check item 2: no Gold-top-300/current-membership look-ahead is required,
   and it is exactly what is present.

2. **[strategies/robustness.py:138-148; strategies/run_residual_reversion.py:501-556] Top-3 contributor removal is registered and counted but never executed.**
   `build_variant_registry` emits `drop_top_{fm}_h{h}` variants whose params carry
   `drop_top_pnl` (`robustness.py:146`). `_run_variant` merges those params
   (`run_residual_reversion.py:507` `vc.update(vs.params)`) but never reads `drop_top_pnl`
   and never calls `remove_top_pnl_contributors` (only imported at
   `run_residual_reversion.py:453`). The drop-top variants therefore run the identical
   backtest as their baseline (same factor model, hold, universe 300, 1× cost) and are
   counted in `n_trials` as if they were a distinct, executed stress. The "top-3
   contributor removal" measure in DeepSeek-must-check item 5 is fabricated.

3. **[strategies/robustness.py:478-570; strategies/run_residual_reversion.py:454-458] Report omits the required measures and columns.**
   `render_robustness_report` emits only a single "Variant results" table. The separate
   tables mandated by BUILD change 4 — factor-model comparison, cost stress, universe
   stress, threshold/window perturbations, top-3 removal, five walk-forward folds,
   exposures, turnover/capacity/margin, and rank IC — are absent. `compute_fold_metrics`,
   `compute_exposures`, `compute_capacity`, `compute_rank_ic` are imported
   (`run_residual_reversion.py:454-458`) but never called, so per-fold Sharpe, exposures,
   capacity and rank IC appear nowhere in any output. The variant row header
   (`robustness.py:522-524`) also omits the mandated IS Sharpe / OOS Sharpe / OOS/IS-ratio
   columns, and the `oos_ratio_min` gate is always `N/A` because `gate_metrics`
   (`robustness.py:547-552`) never supplies `is_sharpe`/`oos_sharpe`.

4. **[strategies/config.yaml:39,42,43; strategies/run_residual_reversion.py:43-48,265] Dead residual config keys + CostParams not wired into the primary backtest.**
   `min_obs_fraction`, `target_gross`, and `execution_lag_bars` are validated by
   `_RESIDUAL_VALID_KEYS` (`run_residual_reversion.py:43-48`) but never consumed:
   `target_gross` is hardcoded `1.0` (`:265`), the one-bar lag is hardcoded `shift(1)`
   (`strategies/backtest.py:42`), and `min_obs` is hardcoded `ceil(0.8*window)`
   (`strategies/residual_reversion.py:136` OLS, `:292` PCA). Separately, `run_one`
   (`run_residual_reversion.py:262-267`) calls `run_backtest` without `cost_params`, so
   the backtest falls back to default `CostParams()` (`strategies/backtest.py:189-190`); the
   config-derived `build_cost_params(cfg)` (`:372`) is used only inside `_run_variant`'s
   cost-stress branch (`:539`). "CostParams is built from config rather than defaults"
   (BUILD change 1) is only partially met — editing `cost_model` in config would not change
   the baseline result. The "every key consumed" test (`tests/strategies/test_robustness.py:411-422`)
   only asserts key *existence*, not consumption, so these dead keys go uncaught (spec
   requires spying on the runner call path).

## Answers to the DeepSeek-must-check list

1. **PCA point-in-time integrity: PASS.** `compute_pca_residuals` fits Ledoit-Wolf and the
   eigendecomposition on `train_slice = returns.iloc[t-window:t]` only
   (`strategies/residual_reversion.py:303-349`), applies frozen means/scales/loadings to
   day t, and orients eigenvectors deterministically (largest-abs loading positive,
   `:339-343`). Within a day the residual is invariant to the sign ambiguity
   (`F_train→-F_train` ⇒ `loadings_j→-loadings_j`, dot product unchanged). Day-t and
   post-t perturbations cannot move the loadings used at t. Tests
   `test_pit_loading_integrity` and `test_perturb_future_does_not_change_past_outputs`
   (`tests/strategies/test_pca_residual_reversion.py:66-126`) cover both and pass.
2. **Universe-size integrity: FAIL.** See blocking finding 1.
3. **Trial counting: PARTIAL.** Within the robustness report `n_trials = len(registry) = 72`
   (6 baseline + 12 cost + 12 universe + 36 parameter + 6 drop-top), and it is passed
   consistently to every reported DSR. But (a) the drop-top trials execute nothing
   (finding 2), and (b) the normal (non-robustness) report uses `n_trials=3` (holds only)
   while the gated breadth ablation is a further evaluated configuration that is not in
   any ledger.
4. **Cost stress correctness: PASS (scaling), with the wiring caveat in finding 4.**
   `compute_costs` → `_scale_params` (`strategies/backtest.py:160-169`) scales
   commission/spread/slippage/borrow exactly once and leaves `adv_participation_cap`
   untouched; `_run_variant` recomputes `net = gross − costs["total"]` once
   (`run_residual_reversion.py:539-546`), so participation limits and gross P&L are
   unchanged and there is no double subtraction. Verified by `test_cost_scales_once`.
5. **Config/gates/tests: FAIL.** Dead keys and un-wired CostParams (finding 4); report gate
   `max_drawdown_max`/`return_to_dd_min` use correct `abs()` signs
   (`strategies/robustness.py:433,444`). Tests pass with pyspark hidden (below), but the
   top-3 measure and report tables are missing (finding 3).

## Non-blocking notes

- `pca_components` is not range-validated to [10,15] despite the spec ("validated
  configured K in [10,15]"); `--pca-components` and `compute_pca_residuals` accept any
  int, and `test_invalid_k_raises_or_returns_fewer` asserts graceful handling rather than
  a raise.
- `_run_variant` recomputes `n_trials = len(build_variant_registry(cfg))` per variant
  (`run_residual_reversion.py:526`); redundant but consistent.
- The registry dedup relies on the baseline loop naturally skipping 1× cost / top-300 /
  unperturbed; the fingerprint set is a correct safety net and `test_unique_fingerprints`
  passes.

## Checks run
```
$ python3 -m pytest -q -p no:cacheprovider tests/strategies tests/ml
127 passed, 34 warnings in 84.75s

$ PYTHONPATH=/tmp/pyspark-hide python3 -m pytest -q -p no:cacheprovider tests/strategies tests/ml
   (sitecustomize sets pyspark/pyspark.sql/pyspark.sql.functions/pyspark.sql.types = None)
127 passed, 34 warnings in 81.06s

$ git grep -n 'screen_universe' strategies/run_residual_reversion.py     # -> no match (never called)
$ git grep -n 'min_obs_fraction\|target_gross\|execution_lag_bars' strategies/run_residual_reversion.py
   # -> only present in _RESIDUAL_VALID_KEYS / config; never read into a call
$ git ls-tree --name-only 9df2030^ -- strategies/robustness.py tests/strategies/test_robustness.py \
    tests/strategies/test_pca_residual_reversion.py                      # -> empty (old code lacks these)
$ git show 9df2030^:strategies/residual_reversion.py | grep -c compute_pca_residuals  # -> 0
```
===VERDICT END===
