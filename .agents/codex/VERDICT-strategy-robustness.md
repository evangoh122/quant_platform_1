===CODEX VERDICT START===
CHANGES_REQUESTED

Blocking findings:

1. PCA loadings depend on day-t data availability.

   - `strategies/residual_reversion.py:310` includes `day_t.notna()` when selecting the symbols used to fit the loading matrix.
   - Independent probe: changing one day-t return to `NaN`, while changing nothing before t, changed the loading matrix at t from 120 rows to 110 rows.
   - This violates the required `[t-window, t-1]` fitting boundary. Day-t availability may determine whether a residual can be produced, but must not change the fitted loadings.
   - The existing PIT test only perturbs a finite value, so it misses this failure.

2. The promised unused-`compute_*` guard is absent.

   - `tests/strategies/test_robustness_round3.py:8` claims every imported `compute_*` helper is checked for actual use, but the tests beginning at `:163` only validate rendered content and required tables.
   - Static call analysis found these imports in `strategies/run_residual_reversion.py:507-519` are not called by `main`: `compute_capacity`, `compute_exposures`, `compute_fold_metrics`, `compute_margin_bps`, `run_cost_stress`, `run_parameter_stress`, and `run_universe_stress`.
   - No AST/source assertion exists to fail when another unused `compute_*` is introduced. Therefore the requested mutation guard is not effective.

Additional spec gap:

- `strategies/residual_reversion.py:291-292` and `strategies/run_residual_reversion.py:394,410` do not validate configured PCA component count to `[10, 15]`. The current test explicitly permits `n_components=0`, contrary to the BUILD specification.

Checks that passed:

- DeepSeek check-5: APPROVED.
- Normal suite: 165 passed, 34 warnings.
- Suite with pyspark hidden: 165 passed, 34 warnings.
- Trial-count duplicate case: 72 registry entries and 72 distinct fingerprints.
- Cost stress: gross unchanged; turnover and borrow costs scaled exactly 2× and 3×.
- Universe, missing-session, Rank-IC/HAC, and drop-top-3 focused probes: 10 passed.
- Rank IC uses forward residual sums and HAC reduces the overlapping-data t-stat.
- Per-fold drop-top-3 selects using training-window realised trade P&L and compares OOS net with net.
- Report language correctly states gates are not evidence or a claim of edge, and gate outputs are PASS/FAIL/N/A.
- Worktree remained unchanged.
===CODEX VERDICT END===
