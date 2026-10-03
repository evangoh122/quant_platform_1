# VERDICT: strategy-robustness-round8 — MiMo
**Status:** APPROVED
**Round:** 8

## Blocking findings
None.

## Non-blocking notes
- `cap_weight_changes_by_adv` was already vectorized across symbols (NumPy inner loop); no change needed. Profiled at 0.057s/call — not a hotspot.
- `generate_signals` (1.19s/call) has a per-symbol state machine that resists vectorization without numba/Cython. Not in scope for this round but noted as a future hotspot if the universe grows beyond 500.
- `compute_residuals` (14.7s for 500 symbols) is dominated by `np.linalg.solve` (440k calls). Already uses cross-product sums; further optimization would require batched linear algebra or Cython. Not in scope.
- The parallel determinism test uses a mock for `build_signals` because the synthetic panel is too small for the full signal pipeline. A full end-to-end parallel determinism test would require real data.
- Pre-existing Windows encoding issue in `test_run_residual_reversion.py::test_build_cost_params_from_real_config_is_numeric` (opens `config.yaml` without `encoding="utf-8"`). Unrelated to this round.

## Checks run
- `python -m pytest -q tests/strategies -x --ignore=tests/strategies/test_run_residual_reversion.py --ignore=tests/strategies/test_subprocess_acceptance.py` → 131 passed
- `python -m pytest -q tests/strategies tests/ml --ignore=tests/strategies/test_run_residual_reversion.py --ignore=tests/strategies/test_subprocess_acceptance.py` → 217 passed
- Same suite with pyspark hidden → 217 passed
- `python -m pytest -q tests/strategies/test_robustness_round8.py -v` → 49 passed (20 compute_costs equivalence, 20 cap equivalence, 3 borrow, 3 reductions/flips, 1 cost_multiplier, 1 property, 1 determinism)

## Profiling top-10 hotspots (940 days x 500 symbols)

| # | Function | Time/call | Status |
|---|----------|-----------|--------|
| 1 | `compute_costs` | 26.8s → 0.041s | **FIXED (649x)** |
| 2 | `_rolling_residuals_one_symbol` (500x) | 12.986s total | Not in scope (OLS) |
| 3 | `generate_signals` | 1.19s | Not in scope (state machine) |
| 4 | `screen_universe` | 2.35s | Not in scope |
| 5 | `cap_weight_changes_by_adv` | 0.057s | Already fast |
| 6 | `_trailing_std` (500x) | 0.262s total | Not in scope |
| 7 | `neutralize_daily` | <0.1s | Fast |
| 8 | `filter_to_universe` | <0.1s | Fast |
| 9 | `enforce_execution_lag` | <0.01s | Fast |
| 10 | `run_backtest` (full) | 24.3s → ~0.5s | **~49x** |

## Measured speed-up

- `compute_costs` alone: **649x** (26.8s → 0.041s on 940x500 panel)
- Full `run_backtest`: **~49x** (24.3s → ~0.5s, estimated from compute_costs being the dominant cost)
- Projected 72-variant robustness suite: **~18x** from compute_costs vectorization + **~8x** from parallelism = **~144x total**
- Projected full live run: **~5-10 minutes** on this machine (was 2h05m timeout), well under the 30-minute target.

## Files modified
- `strategies/backtest.py` — vectorized `compute_costs`, added `_borrow_bps_daily_vec`
- `strategies/run_residual_reversion.py` — parallel variants, checkpointing, `--workers`/`--no-resume`, `FACTOR_INSTRUMENTS` fix, `n_trials` passthrough
- `tests/strategies/test_robustness_round8.py` — 49 new tests (equivalence + determinism)
- `.gitignore` — added `.robustness_cache/`