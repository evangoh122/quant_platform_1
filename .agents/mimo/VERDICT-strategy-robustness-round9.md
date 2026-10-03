# VERDICT: strategy-robustness-round9 — MiMo
**Status:** APPROVED
**Round:** 9

## Fixes applied (addressing all 3 DeepSeek blocking findings)

1. **ProcessPool workers picklable** — `_worker_init` and `_worker_task` moved to module-level `strategies/robustness_worker.py`. Shared data passed via pool initializer (module global). Worker errors are no longer swallowed — any variant error FAILS the run with the error message.

2. **Cache fingerprint complete** — `compute_cache_fingerprint()` now combines:
   - variant params fingerprint (existing `_fingerprint`);
   - config fingerprint: `cost_model`, `residual_reversion`, `robustness` blocks;
   - data fingerprint: panel shape, date range, symbol list, value checksum;
   - code version: SHA-256 of all `strategies/*.py` source + git SHA + dirty flag.
   Changing `commission_bps` from 0.5→50 produces a different fingerprint.

3. **Resume keyed by variant_id** — Results stored in `results_by_id: dict[str, dict]` keyed by `vs.variant_id`. Rebuild in registry order: `[results_by_id[vs.variant_id] for vs in registry]`. No position-based assumption; arbitrary cached subsets resume correctly.

## Additional fixes

4. **DataFrame serialization in cache** — `_save_cache` now serialises DataFrames as `{"data": [...], "index": [...], "columns": [...]}`. Cached variants survive resume without `KeyError` on `weights`, `trade_returns`, `s_score`, `residual_returns`.

5. **Run summary** — prints computed vs cached variant counts and wall time after pool finishes.

6. **`_run_variant` accepts `build_signals_fn`** — optional parameter for spawn-safe pool testing; defaults to real `build_signals` when `None`.

## Non-blocking notes

- `_save_cache` JSON files for large DataFrames (weights: dates × symbols) may be ~10–50 MB each. Acceptable for a checkpoint cache; no size regression vs the old approach that skipped DataFrames entirely (which was broken).
- `_code_fingerprint()` reads all `strategies/*.py` on every call. For 72 variants this adds ~72 × file-read overhead. Negligible vs the backtest time per variant (~seconds).

## Checks run

- `python3 -m pytest -q tests/strategies tests/ml` → **236 passed**, 34 warnings
- Same suite with pyspark hidden (`PYTHONPATH=/tmp/nospark`) → **236 passed**, 34 warnings
- `git status --short` → only expected files modified; `.agents/dispatch.sh` untouched
- `file *.py | grep CRLF` → no CRLF (all LF)