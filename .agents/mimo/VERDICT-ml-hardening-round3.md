# VERDICT: ml-hardening-round3 — MiMo
**Status:** APPROVED
**Round:** 3

## Blocking findings
None.

## Non-blocking notes
- The FutureWarning about setting items of incompatible dtype (bool → float) on `sec_material_event` during neutralisation is pre-existing and unrelated to this round. Worth addressing separately.
- 5/170 timestamps skipped in the default synthetic run (early bars where forward returns aren't yet available — not a neutralisation bug, just data sparsity at the start of the series).

## Checks run
- `python3 -m pytest tests/ml -q -m "not spark and not databricks"` → 28 passed, 14 warnings
- `python3 -m ml.run_ablation --n-symbols 18 --n-bars 200 --seed 42` → neutralisation counts: 165 neutralised, 5 skipped (out of 170). Post-neutralisation correlation with beta effectively zero on neutralised timestamps.

## Changes made

### `ml/features.py`
- Dropped intercept from design matrix in `neutralize_features` to avoid dummy-variable trap (beta + K industry dummies, not + intercept). Minimum viable cross-section is now K+1, not K+2.
- Added neutralised/skipped timestamp counting with WARNING log when any are skipped, ValueError raise when ALL are skipped.
- `_report_beta_correlations` now accepts `only_timestamps` filter; "after" stage reports only neutralised timestamps.
- Added counts log line after neutralisation completes.

### `ml/synthetic_data.py`
- Default `n_symbols` increased from 6 to 18 (= 3 × (1 + n_industries)).

### `ml/run_ablation.py`
- Default `--n-symbols` increased from 6 to 18.

### `tests/ml/test_hardening.py`
- `test_underdetermined_cross_section_raises`: verifies that all-skipped timestamps raise ValueError.
- `test_mixed_underdetermined_cross_section_warns`: verifies mixed case logs WARNING with counts.
- `test_real_runner_neutralises_timestamps`: verifies real runner path neutralises > 0 timestamps and post-neutralisation mean |corr(feature, beta)| < 1e-6.

### `tests/ml/test_ablation.py`
- Updated `test_ablation_runner_varies_feature_set_between_arms` to use `n_symbols=18` (was 4, now correctly caught as underdetermined).