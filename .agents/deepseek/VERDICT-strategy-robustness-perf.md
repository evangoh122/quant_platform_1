===VERDICT START===
# VERDICT: strategy-robustness-perf (round 8 + performance) — DeepSeek
**Status:** CHANGES_REQUESTED
**Round:** 8 (perf check)

Read-only verification of `85e654b` (parallel variants + checkpointing) and `0eda687`
(vectorized `compute_costs`) on branch `slice/strategy-robustness`. The **vectorisation is
correct** (numerical equivalence to the old `67a25f8` loop implementation is exact), and all 231
tests pass with and without pyspark. But the two headline *new* features — the ProcessPool
parallel execution and the checkpoint/resume — are broken in ways that no test covers. Four
blocking findings below.

## Blocking findings

- [strategies/run_residual_reversion.py:623,665] **Parallel path is non-functional.**
  `_worker_task` (and `_worker_init`) are nested inside `main()`. `ProcessPoolExecutor` pickles
  the submitted callable, and nested functions cannot be pickled, so every
  `pool.submit(_worker_task, w)` raises
  `AttributeError: Can't pickle local object 'main.<locals>._worker_task'`. Because the exception
  is swallowed at `:671-674`, a real `--robustness` run silently turns every one of the 72 variants
  into `{"error": "Can't pickle local object ..."}` and renders an all-ERROR report. Reproduced
  standalone with the exact nested-function pattern (fork start method, Python 3.12) — fails
  identically. No test exercises this path: `test_robustness_round8.py::test_workers_determinism`
  deliberately runs sequentially twice instead of using ProcessPool (comment at
  `tests/strategies/test_robustness_round8.py:388-391`). So the requested "workers=1 == 4 == 8"
  guarantee is not just untested — the mechanism cannot run at all.

- [strategies/robustness.py:38-41, strategies/run_residual_reversion.py:638,678] **Checkpoint
  fingerprint does not cover config / data / code version.** `_fingerprint` hashes only the
  variant `params` dict (`factor_model, max_hold, universe_size, cost_multiplier, entry_threshold,
  exit_threshold, factor_window`). It omits every `cost_model` parameter, the input data, and the
  code version. Proven: `_fingerprint` for `baseline_ols_mkt_ind_h5` is `85d83604c56c` and is
  **unchanged** after setting `cost_model.commission_bps` 0.5→50 and `spread_bps` 3→300. A changed
  cost param therefore reuses the stale cached variant, directly violating the requirement "a
  changed input must not reuse a stale cache".

- [strategies/run_residual_reversion.py:692-702] **Partial-resume reorders results onto the wrong
  variants.** The `ordered_results` rebuild assumes the cached variants form a contiguous prefix of
  registry order (`if cache_idx < skipped`). After a crash mid-run the cache holds an arbitrary,
  non-prefix subset (variants complete in `as_completed` order). Reproduced: registry `[A,B,C,D]`
  with cached `{A,C}` rebuilds to `[A_CACHED, C_CACHED, B_RUN, D_RUN]` — B gets C's cached result
  and C gets B's computed result. The report's per-variant rows and the rank-IC / drop-top3 loops
  (`zip(registry, variant_results)`) then attribute wrong numbers to wrong variants, so cached
  results appear twice and computed results are lost.

- [strategies/run_residual_reversion.py:597-610,733-734] **Cached variants drop the frames the
  post-processing needs.** `_save_cache` skips every `pd.DataFrame`/`pd.DatetimeIndex` (line
  `:603-604`), so a cached variant has no `weights`, `trade_returns`, `s_score`, or
  `residual_returns`. On resume, the drop-top3 loop reads `hold_vr["weights"]` (`:733`) and
  `hold_vr["trade_returns"]` (`:734`) → `KeyError`, crashing `main()`. The rank-IC loop
  (`:707-718`) instead reads via `.get(...)` → `None`, silently producing an empty Rank-IC table.
  Checkpointing therefore cannot actually resume to a complete report.

## Verified correct (non-blocking)

- **Numerical equivalence (req 1) — PASS.** Independent `/tmp` comparison of the new `compute_costs`
  vs the old `git show 67a25f8:strategies/backtest.py` loop version on **600 random panels × 3
  multipliers (1×/2×/3×) = 1800 runs**, covering NaN ADV, zero ADV, sign flips, reductions, exits
  and short borrow. Max absolute difference `8.88e-16` (vs 1e-10 tolerance). The `_borrow_bps_daily_vec`
  bucket boundaries (`>= 5e7` liquid, `>= 2e7` medium) match `liquidity_bucket` exactly, including
  NaN→0 handling.
- **Determinism (req 2) — holds by construction, not by test.** No `np.random`/`random.*`/`RandomState`
  anywhere under `strategies/`; each worker's `_WORKER_DATA` is set per-process in the initializer
  (no shared mutable state); results are re-sorted into registry order. So the pipeline *would* be
  deterministic if the ProcessPool path ran — but it currently cannot (finding 1). Note the request's
  "seeds are per variant" is inaccurate: there are no seeds.
- **Cache dir gitignored (req 3) — PASS.** `.gitignore` line `strategies/results/.robustness_cache/`
  is present. `--no-resume` correctly bypasses both `_load_cache` (`:637`) and `_save_cache` (`:677`).
- **Trial counting (req 4) — count preserved, association broken.** `n_trials = len(registry)` is
  constant and each variant is either cached or run once (no double-count of the DSR penalty), but
  findings 3–4 show the *association* of results to variants is wrong on partial resume.
- **Property tests + earlier guarantees (req 5) — PASS.** Full suites below.

## Checks run

- `python3 -m pytest -q tests/strategies tests/ml` (repo root) → **231 passed**, 34 warnings
- Same suite with pyspark hidden (`PYTHONPATH=/tmp/nospark`, sitecustomize `sys.modules["pyspark*"]=None`)
  → **231 passed**, 34 warnings
- Independent equivalence: 600 cases × 3 multipliers vs `git show 67a25f8` → worst abs diff `8.88e-16`
- Fingerprint-coverage demo: `_fingerprint` unchanged after `cost_model.commission_bps` 0.5→50 /
  `spread_bps` 3→300 → **FAIL** (same fingerprint `85d83604c56c`, stale cache would be reused)
- Interleaved-resume demo: registry `[A,B,C,D]`, cached `{A,C}` → rebuilt `[A_CACHED, C_CACHED, B_RUN, D_RUN]`
  → **FAIL** (B/C swapped)
- Pickle repro (nested `_worker_task` + `ProcessPoolExecutor`, fork) → **FAIL**
  (`Can't pickle local object 'main.<locals>._worker_task'`)
- `git status --short` → only `.agents/dispatch.sh` modified (pre-existing; not touched here)
===VERDICT END===
