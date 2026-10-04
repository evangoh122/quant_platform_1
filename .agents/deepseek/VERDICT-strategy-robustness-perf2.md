Checker: Claude Sonnet subagent (DeepSeek out of credit)

===VERDICT START===
# VERDICT: strategy-robustness-perf, re-check after round 9
**Status:** CHANGES_REQUESTED

Round 9 (e9e10ac) fixes the three prior findings that were checked: pool pickling, fingerprint coverage of cost params, and keyed resume. My own proofs confirm each fix. However, the checkpoint round-trip I tested while verifying "resume maps each variant to its own result" turned up two further defects. Both silently produce a wrong report on a resumed run, so I am requesting changes. All scratch proofs are in `/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/chk-robust/`.

## Blocking findings

- [strategies/run_residual_reversion.py:584-627 (`_load_cache`/`_save_cache`), consumed at :736-737] **Cache round-trip destroys the date indexes, so a resumed run silently gives a different report than a fresh run.**
  `_save_cache` writes Series as bare `tolist()` and DataFrames with `str(index)`. `_load_cache` rebuilds `net`/`gross`/`turnover` with a RangeIndex and `weights`/`s_score`/`trade_returns`/`residual_returns` with an object (string) index, and `industry` and `adv_wide` come back as `list`/`dict`, not Series/DataFrame. I ran a real `_run_variant` result through the actual `_save_cache`/`_load_cache` source (extracted by text):
  `net` index DatetimeIndex -> RangeIndex, `.equals` False for every Series/DataFrame, and `net.reindex(dates).notna().sum()` is 0 for the cached copy versus 200 for the fresh copy.
  Failure scenario: after a crash and resume, the baseline variants come from cache. The drop-top-3 loop does `net_full.reindex(train_dates).dropna()`. That is empty, so `if train_net.empty: continue` skips every fold, and the drop-top-3 section is silently empty. Rank-IC reads date-indexed frames that now have string indexes. Nothing errors, so a resumed run differs from a fresh run with no warning. (`compute_fold_metrics` is positional and happened to match.)
  Fix: persist with a type-preserving format (e.g. `pickle`, `DataFrame.to_parquet`, or `to_json(orient="split", date_format="iso")` with `pd.to_datetime` on load). Drop `adv_wide`/`industry` from the checkpoint, since they are inputs and not results. Add a test that a fresh `_run_variant` result and a save/load round trip give `assert_series_equal` / `assert_frame_equal` on every field. Better: move the cache helpers to module level in `robustness.py` so they are testable.

- [strategies/run_residual_reversion.py:637 (`compute_cache_fingerprint(vs.fingerprint, cfg, panel)`)] **The fingerprint omits the CLI overrides, so a stale cache is reused.**
  `--book-capital` (and `--factor-model` / `--pca-components`) override values outside `cfg`. `book_capital` is passed to `_run_variant` and drives costs and capacity, but it is not part of the fingerprint inputs (variant params, `cost_model`/`residual_reversion`/`robustness` config blocks, panel, code). Failure scenario: run `--robustness`, then rerun with `--book-capital 5e6`. Every variant is served from the old 1e7 cache, and the report is labelled with the new capital but contains the old numbers.
  Fix: pass the effective `book_capital`, `factor_model` and `pca_components` (or the effective `cfg` after overrides) into `compute_cache_fingerprint`. Add a test that varies each.

## Non-blocking notes

- `_data_fingerprint` (`robustness.py` ~:55-68) hashes only shape, date range, the first 20 symbols, and `close.sum()`. Proven: doubling `dollar_volume` (which drives universe screening) does not change the fingerprint, and a sum-preserving edit of `close` (+1/-1 on two rows) does not change it. Prefer `pd.util.hash_pandas_object(panel[["symbol","event_date","close","dollar_volume"]]).sum()`. `closes`/`universe`/`adv_wide` are not hashed directly, only through `panel`.
- `TestResumeOrdering` only exercises a hand-built dict and `[results_by_id[vs.variant_id] ...]`. It does not call the real main-loop code. `main()`'s cache and pool wiring is untested. The keyed rebuild itself is correct on read-through (`results_by_id[vs.variant_id]`, :~690), and my keyed check gave each variant its own result.
- `TestParallelDeterminism` compares only `net` at workers 1 vs 2 and uses 4 variants of identical fake signals. My broader proof (below) compared all fields and workers 1/2/4. Add 4 to the test.
- `main()` uses the platform default start method (fork on Linux). Python 3.14 defaults to forkserver. Worker functions are module-level, so this is fine, but consider pinning `mp_context`.
- "Executed trials: 0" in a fully cached run could be misread as zero trials. The line "Total unique trials" is correct. Consider labelling it "computed this run".
- `git diff --quiet` in `_code_fingerprint` ignores untracked files, but the source-hash of `strategies/*.py` covers them, and `ml/` imports are not hashed. Acceptable.

## Checks run

1. Equivalence: new `compute_costs` vs old (`git show 67a25f8:strategies/backtest.py`), 700 random panels x 3 multipliers (1x/2x/3x) = 2100 cases, 6300 series compared (NaN ADV, zero ADV, flips, reductions, exits, shorts; mixed ADV buckets). Max abs diff **5.3e-15** (tolerance 1e-10); index and NaN positions identical. PASS.
2. Pool determinism, real `ProcessPoolExecutor` with `_worker_init`/`_worker_task` from `robustness_worker.py`: 10 variants, spawn and fork, workers 1/2/4; every field of every result (Series, DataFrames, dicts, scalars) identical to the spawn/1 baseline in all 6 configs. PASS. Injected `build_signals_fn` that raises: `future.result()` raised `ValueError: injected`, so the run fails (the main loop calls `future.result()` with no try/except, and raises on any `"error"` dict). Errors are not swallowed. PASS.
3. Fingerprint: changing `cost_model.commission_bps`/`spread_bps`/`slippage_bps`/`adv_participation_cap`, `residual_reversion.book_capital`/`execution_lag_bars`, `robustness.rank_ic_horizon_days`, or a `close` value each changes the fingerprint. The code fingerprint is stable across calls. PASS for config, close and code. FAIL for CLI overrides (blocking 2) and weak data coverage (note 1).
4. Resume: keyed-by-name rebuild gives correct per-variant mapping (non-prefix {A,C} cached). PASS by code read and by the unit test, but the cached payload itself is corrupted on load (blocking 1).
5. Trial counting: `n_trials = len(registry)` is passed to every variant and the report regardless of cache hits. DSR is recomputed at render time from `net` with `n_trials=len(registry)` (`robustness.py:665`). Each variant is cached or run exactly once. Unchanged by caching. PASS.
6. `python3 -m pytest -q -p no:cacheprovider tests/strategies tests/ml` -> **236 passed**, 34 warnings (124s). The pyspark-hidden run was not repeated (not requested in this brief).
7. `.gitignore` covers `strategies/results/.robustness_cache/` (verified via `git check-ignore`). Repo working tree untouched by this check (only this verdict file added).
===VERDICT END===
