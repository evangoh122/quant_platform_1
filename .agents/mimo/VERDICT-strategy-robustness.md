# VERDICT: strategy-robustness — MiMo
**Status:** APPROVED
**Round:** 1

## Changed files
- `strategies/config.yaml` — residual_reversion primary block, cost_model borrow params, metric_gates, robustness section, experimental_strategies
- `strategies/residual_reversion.py` — added `compute_pca_residuals()` with Ledoit-Wolf shrinkage, causal PIT fitting
- `strategies/run_residual_reversion.py` — added `load_strategy_config`, `build_cost_params`, `validate_residual_config`, `--config`/`--factor-model`/`--pca-components`/`--robustness` flags, `build_signals` dispatch
- `strategies/robustness.py` — new pure library: `VariantSpec`, `build_variant_registry`, `run_cost_stress`, `run_universe_stress`, `run_parameter_stress`, `remove_top_pnl_contributors`, `compute_fold_metrics`, `compute_exposures`, `compute_capacity`, `compute_margin_bps`, `compute_rank_ic`, `evaluate_gates`, `render_robustness_report`
- `docs/QUANT_STRATEGIES.md` — residual mean-reversion marked as primary built strategy
- `tests/strategies/test_pca_residual_reversion.py` — 8 PCA PIT tests
- `tests/strategies/test_robustness.py` — 37 robustness library + config tests
- `tests/strategies/test_subprocess_acceptance.py` — 1 subprocess acceptance test (pyspark mocked)
- `tests/strategies/test_run_residual_reversion.py` — 6 config helper tests added

## Blocking findings
None.

## Non-blocking notes
- `.agents/dispatch.sh` shows a file-mode-only change in git (executable bit flip from WSL/Windows interaction); content is unchanged.
- The pre-existing CRLF files (`.pytest_cache/README.md`, `api/models/schemas.py`) are not touched by this change.
- The robustness report's `_run_variant` in the runner is a convenience wrapper; the pure library functions in `strategies/robustness.py` are independently testable.

## Old-code failure proof
Pre-change checkout (commit before 9df2030) with new test files added:
```
ERROR test_pca_residual_reversion.py
  ImportError: cannot import name 'compute_pca_residuals' from 'strategies.residual_reversion'
ERROR test_robustness.py
  ModuleNotFoundError: No module named 'strategies.robustness'
```

## Checks run
- `python -m pytest -q tests/strategies` → 88 passed
- `python -m pytest -q tests/ml/test_walk_forward.py tests/ml/test_hardening.py` → 26 passed
- `python -m pytest -q tests/strategies tests/ml` → 125 passed
- `python -m compileall -q strategies ml` → pass (no output)
- LF endings check on all changed files → pass (no CRLF)
- `git diff --check` → pass (no output)

## Commit SHA
9df2030 (implementation), f0f7745 (verdict)