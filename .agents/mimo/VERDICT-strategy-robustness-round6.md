# VERDICT: strategy-robustness-round6 — MiMo
**Status:** APPROVED
**Round:** 6

## Blocking findings
- None remaining. All three blocking findings from the Codex verdict are fixed.

## Fixes applied

### 1. PCA loadings depend on day-t availability [BLOCKING]
- `strategies/residual_reversion.py:310` — removed `& day_t.notna()` from `valid_mask`.
- Symbol eligibility for the FIT now uses only `[t-window, t-1]`. Day-t NaN returns produce no residual but never change the fitted loading matrix.
- `day_t_std` is cleaned (`np.where(np.isfinite(...))`) before factor projection so NaN does not contaminate `day_t_factors`.
- Loadings are still recorded for symbols with NaN day-t (fitted from lagged data).

### 2. Unused `compute_*` guard [BLOCKING]
- Removed 8 dead imports from `strategies/run_residual_reversion.py:507-519`: `run_cost_stress`, `run_universe_stress`, `run_parameter_stress`, `compute_fold_metrics`, `compute_exposures`, `compute_capacity`, `compute_margin_bps`, `evaluate_gates`. These are already called inside `render_robustness_report` in `strategies/robustness.py`.
- Removed dead `VariantSpec` import from `_run_variant`.
- Added AST-based test `TestUnusedComputeImportGuard.test_no_unused_robustness_imports` that parses `run_residual_reversion.py` and fails if any imported name from `strategies.robustness` is not used. Mutation: adding an unused `compute_*` import fails the test.

### 3. PCA component count validated to [10, 15] [SPEC]
- `strategies/residual_reversion.py:compute_pca_residuals` now raises `ValueError` if `n_components` is outside `[10, 15]`.
- `strategies/run_residual_reversion.py:validate_residual_config` now raises `ValueError` if `pca_components` is outside `[10, 15]`.
- Fixed `test_pca_residual_reversion.py::test_invalid_k_raises_or_returns_fewer` to expect `ValueError` for `n_components=0`.
- Updated all tests using `n_components < 10` to use `n_components=10` with `n_symbols=20`.

## Non-blocking notes
- The 7 functions (`compute_capacity`, `compute_exposures`, etc.) are not dead code — they are called inside `render_robustness_report` in `strategies/robustness.py`. The dead imports in the runner were the issue, now removed.

## Checks run
- `python3 -m pytest tests/strategies tests/ml -q` → 175 passed, 34 warnings
- Same suite with pyspark hidden (test_subprocess_acceptance.py ignored) → 174 passed, 34 warnings
- LF line endings verified on all modified files (no CRLF)
- No scratch files left in worktree