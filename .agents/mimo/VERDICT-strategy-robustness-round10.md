# VERDICT: strategy-robustness-round10 — MiMo
**Status:** APPROVED
**Round:** 10

## Blocking findings
- None. Both blocking defects from the Claude/DeepSeek verdict are fixed.

## Fixes implemented

### 1. Cache round-trip preserves date indexes
- **`strategies/robustness.py:100-133`**: Added `save_variant_cache()` and `load_variant_cache()` using `pickle` (type-preserving). Pickle natively preserves `DatetimeIndex`, `MultiIndex`, and all pandas/numpy types. Input-only fields (`adv_wide`, `industry`) are dropped from the checkpoint to reduce file size.
- **`strategies/run_residual_reversion.py:580-600`**: Removed the old nested `_save_cache`/`_load_cache` (JSON-based, lossy). Now calls `save_variant_cache`/`load_variant_cache` from `robustness.py`.

### 2. CLI overrides in fingerprint
- **`strategies/robustness.py:97-113`**: `compute_cache_fingerprint()` now accepts optional `effective_overrides` dict. When provided, it's hashed into the composite fingerprint.
- **`strategies/run_residual_reversion.py:584-591`**: Passes `effective_overrides = {"book_capital": book_capital, "factor_model": factor_model, "pca_components": pca_components}` to `compute_cache_fingerprint()`.

### 3. Data fingerprint covers full panel values
- **`strategies/robustness.py:55-69`**: `_data_fingerprint()` now uses `pd.util.hash_pandas_object()` on `close` AND `dollar_volume` columns (sorted by date/symbol), replacing the old weak checksum (shape + first 20 symbols + close sum).

### 4. Determinism test expanded to all fields at workers 1/2/4
- **`tests/strategies/test_robustness_round10.py:168-240`**: `TestParallelDeterminismAllFields.test_workers_1_2_4` compares every Series, DataFrame, and scalar field of every variant result at workers=1, 2, and 4 using `atol=1e-10`.

### 5. Executed/cached/total trials reported
- **`strategies/run_residual_reversion.py:695-700`**: Summary now prints: `Executed trials (computed this run): N / cached: M / total counted: K`.

## Non-blocking notes

- The `.pkl` cache files are not backward-compatible with old `.json` cache files. Old cache files in `strategies/results/.robustness_cache/` will be ignored (different extension and different fingerprint due to overrides). No migration needed.
- `adv_wide` and `industry` are dropped from checkpoints since they are inputs, not results. They are re-created from config/data on each run.
- The `effective_overrides` dict is hashed separately from the config, so changing `--book-capital` from 10M to 5M produces a different fingerprint even though `cfg["residual_reversion"]["book_capital"]` still says 10M.

## Checks run

1. `python3 -m pytest -q tests/strategies tests/ml` → **246 passed**, 1 failed (pre-existing: `test_build_cost_params_from_real_config_is_numeric` — Windows cp1252 encoding of UTF-8 em-dash in config.yaml, not related to these changes), 22655 warnings (245s).
2. `python3 -m pytest -q tests/strategies tests/ml -p no:pyspark` → **246 passed**, 1 failed (same pre-existing), 22655 warnings (233s).
3. `python3 -m pytest tests/strategies/test_robustness_round10.py -v` → **11 passed** (53s). All new tests pass:
   - `TestCacheRoundTrip`: 4 tests (round-trip preserves datetime index, preserves metrics, drops input-only fields, resume report identical to fresh)
   - `TestCLIOverrideFingerprint`: 4 tests (book_capital, factor_model, pca_components, no-overrides-unchanged)
   - `TestDataFingerprint`: 2 tests (dollar_volume change, close value change)
   - `TestParallelDeterminismAllFields`: 1 test (workers 1/2/4, all fields)
4. `python3 -m pytest tests/strategies/test_robustness_round8.py::TestParallelDeterminism -v` → **1 passed** (existing test still passes).
5. LF line endings verified on all modified files: `robustness.py`, `run_residual_reversion.py`, `test_robustness_round10.py`.