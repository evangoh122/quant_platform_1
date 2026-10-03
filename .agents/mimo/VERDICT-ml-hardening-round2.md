# VERDICT: ml-hardening-round2 — MiMo
**Status:** APPROVED
**Round:** 2

## Blocking findings
(none — all three defects from the Codex verdict are resolved)

## Non-blocking notes
- `_report_beta_correlations` uses `import logging` inside the function body to avoid a top-level import; acceptable for a diagnostic helper but could be moved to module level if preferred.
- The `periods_per_year=252` default in `evaluate_predictions` is used for the timestamp-aggregated DSR path; if the synthetic bar frequency changes significantly, this may need adjustment (currently correct for daily aggregation of intraday bars).
- The `beta_df` merge uses `pd.to_datetime(..., utc=True)` to match the matrix's `datetime64[ns, UTC]` dtype; this is robust but worth noting as a pandas version sensitivity point.

## Checks run
- `wsl python3 -m pytest tests/ml -q -m "not spark and not databricks"` → 25 passed, 0 failed (12 warnings, all pre-existing deprecation notices)

## Changes made

### 1. Neutralisation no longer silently skips (ml/features.py)
- `neutralize_features` raises `ValueError` when `market_beta` or `industry` is absent.
- New `_report_beta_correlations` helper logs cross-sectional correlation of each feature with beta before and after neutralisation.

### 2. Synthetic data provides market_beta and industry (ml/synthetic_data.py)
- Trailing 20-bar rolling beta computed per symbol against equal-weighted market return.
- Industry assigned from `["tech", "bank", "healthcare", "energy", "consumer"]` round-robin on symbol index.
- New `label_method` parameter (`"fixed"` or `"triple_barrier"`) selects labelling scheme.

### 3. Triple-barrier selectable (ml/run_ablation.py, ml/train.py, ml/registry.py)
- `--label-method {fixed,triple_barrier}` CLI argument (default `fixed`).
- Threaded through `make_synthetic_matrix`, `run_ablation`, `build_run_tags`.
- Logged as MLflow param and recorded in results artifact.

### 4. Honest deflated Sharpe (ml/evaluate.py, ml/train.py)
- `evaluate_predictions` accepts `n_trials` (actual config count) instead of hard-coded 4.
- DSR computed on timestamp-aggregated strategy returns (one mean return per date).
- `run_ablation` computes `n_trials = len(feature_sets) * len(models)` and passes it through.

### 5. Tests (tests/ml/test_hardening.py)
- `test_neutralisation_raises_when_inputs_missing` — verifies ValueError on missing columns.
- `test_neutralisation_reduces_beta_correlation` — post-neutralisation |corr| < 0.15.
- `test_synthetic_matrix_has_market_beta_and_industry` — columns present and populated.
- `test_ablation_uses_triple_barrier_labels` — triple-barrier produces different labels than fixed.
- `test_deflated_sharpe_decreases_with_more_trials` — DSR monotone decreasing in n_trials.