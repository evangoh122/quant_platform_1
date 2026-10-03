===VERDICT START===
# VERDICT: strategy-robustness-check6 — DeepSeek
**Status:** CHANGES_REQUESTED
**Round:** 12 (robustness round-6 re-check)

Re-checked commit `37fb1ef` (MiMo round 6, addressing Codex's three findings) at
HEAD `4999e63` on `slice/strategy-robustness`. Read-only; all scratch under the
open-code temp dir (nothing in the worktree). Nothing committed or pushed.

## The three Codex findings — all FIXED (proofs)

### 1. PCA loadings depend on day-t availability — FIXED
- `strategies/residual_reversion.py:316` — `valid_mask = train_slice.notna().all(axis=0)`
  no longer includes `& day_t.notna()` (removed in 37fb1ef). Symbol eligibility for
  the FIT uses only `[t-window, t-1]`.
- Day-t NaN returns are zeroed only in the projection path
  (`day_t_std_clean = np.where(np.isfinite(day_t_std), day_t_std, 0.0)`, `:366`) and a
  NaN-day symbol still records lagged loadings but no residual (`:368-379`).
- **Independent probe** (factor-dominated 12-symbol panel, window 60, K=10, t=100):
  ```
  day-t NaN : shape_equal=True (base (120,4) vs alt (120,4)), loadings_identical=True
  day-t huge: shape_equal=True (base (120,4) vs alt (120,4)), loadings_identical=True
  ```
  Setting one day-t return to `NaN`/`999.0` leaves the t-dated loading frame identical in
  shape and value; only the day-t residual of the perturbed symbol changes (allowed).

### 2. Unused-`compute_*` guard — FIXED (mutation-proven)
- 8 dead imports removed from `main()` (`run_residual_reversion.py:512-519`) and the dead
  `VariantSpec` import from `_run_variant` (`:660`). The 7 functions remain called inside
  `render_robustness_report` (`strategies/robustness.py`).
- `tests/strategies/test_robustness_round6.py::TestUnusedComputeImportGuard` parses the
  runner with `ast`, collects `ImportFrom` names whose module contains "robustness", and
  asserts none is unused.
- **Mutation probe** (same AST logic as the test):
  ```
  imported from robustness: ['build_variant_registry','compute_rank_ic','remove_top_pnl_contributors','render_robustness_report']
  unused (real source, expect empty): []
  mutation (add unused compute_capacity)   -> unused: ['compute_capacity']
  mutation (add unused compute_exposures)  -> unused: ['compute_exposures']
  ```
  Adding an unused `compute_*` import fails the guard. (Non-blocking note: the guard checks
  "name appears anywhere", not "is called", but it satisfies the round-6 mutation criterion.)

### 3. PCA component count in [10, 15] — FIXED
- `compute_pca_residuals` raises `ValueError` outside [10, 15] (`residual_reversion.py:291-294`).
- `validate_residual_config` raises `ValueError` outside [10, 15] (`run_residual_reversion.py:83-87`).
- **Probe:** `K=0,5,9,16,20` all raise `n_components must be in [10, 15]`; `K=10,15` succeed;
  config `pca_components=0/20` raise `pca_components must be in [10, 15]`.

## NEW blocking finding

1. **[strategies/residual_reversion.py:304,368,390] PCA residual frame is written to the
   wrong column when any symbol is excluded from the fit — column/symbol misalignment.**
   `residual = pd.DataFrame(np.nan, index=dates, columns=symbols)` (`:304`) is keyed by the
   *full* symbol list, but the fill loop iterates `for j, sym in enumerate(valid_syms)`
   (`:368`) and writes `residual.iloc[t, j] = …` (`:390`). `j` is the position within
   `valid_syms` (a subset), not the position of `sym` in `symbols`. Whenever `valid_syms`
   is a proper subset of `symbols` — i.e. any symbol has a NaN in the `[t-window, t-1]`
   training slice — the residual for `valid_syms[j]` lands in column `symbols[j]`, shifting
   every residual, `sigma`, and `s_score` to a different symbol. The `loadings` long frame is
   unaffected (it is keyed by `sym`, `:378,394`).
   - **Concrete failure:** in the live path `build_signals` calls
     `compute_pca_residuals(tradeable_returns, …)` where `tradeable_returns` is the PIT-masked
     universe frame (NaN on non-member dates, `run_residual_reversion.py:229`). Symbols that
     entered the top-N universe recently have NaN gaps in the 60-day window, so
     `valid_mask = train_slice.notna().all(axis=0)` excludes them and the misalignment fires.
   - **Probe proof** (8-symbol panel, NaN injected in `S00` inside the t=100 training window):
     ```
     S00 residual (should be NaN since S00 had NaN in window): 6.07e-18   # S01's residual
     S01 residual (should be finite):                          -2.60e-18
     symbols present in loadings at t: ['S01'..'S07']          # S00 correctly excluded
     residual row: S00..S06 filled, S07 = NaN                  # shifted by one column
     ```
     `S00` (excluded from the fit) nonetheless receives a value, and the last valid symbol
     `S07` is left NaN — definitive column shift.
   - **Impact:** every PCA-lane report quantity is corrupted on real data — PCA baseline/cost/
     universe/parameter/drop-top variant Sharpe, PCA positions, and the PCA rank-IC
     (`s_score` vs `residual_returns` misaligned to each other). The OLS lane is unaffected
     (`compute_residuals` writes `alpha[sym] = …` keyed by symbol, `:246-249`).
   - **Fix:** write `residual.loc[t, sym] = …` (and add a test with a NaN gap in the training
     window asserting per-symbol residual alignment; the existing PCA tests use fully-populated
     panels, so they never trigger the shift).

## Full pass — every report quantity

| Report quantity | Verdict |
|---|---|
| Factor-model net/IS/OOS Sharpe, OOS/IS, DSR (OLS) | **PASS** |
| Factor-model net/IS/OOS Sharpe, OOS/IS, DSR (PCA) | **FAIL** — residual/s_score misaligned (finding 1) |
| Cost stress 2×/3× (commission/spread/slippage/borrow ×1, gross & participation unchanged) | **PASS** (OLS); PCA values inherit the misalignment |
| Universe stress 200/500 (dense-grid `screen_universe` re-screen) | **PASS** for membership; PCA values inherit the misalignment |
| Parameter perturbation ±20% | **PASS** (OLS); PCA values inherit the misalignment |
| Top-3 P&L contributor removal (registry variant) | **PASS** (OLS path, `remove_top_pnl_contributors`); PCA path misaligned |
| Per-fold drop-top-3 (train-window realised P&L, net-vs-net OOS) | **PASS** (verified rounds 5/6; unchanged) |
| Walk-forward folds (`compute_fold_metrics` on purged validation folds) | **PASS** |
| Exposures (dollar `Σw/gross`, beta `Σw·β/gross`, sector `max |net|`) | **PASS** |
| Turnover / capacity / margin | **PASS** |
| Rank IC (forward residual sum t+1..t+H, HAC lag H-1, n & eff. n disclosed) | **PASS** for OLS; **FAIL** for PCA (s_score/residual misaligned) |
| Gate summary + honest trial count (72 unique, dedup by fingerprint) | **PASS** |

Everything OLS passes; the single defect is the PCA column alignment, which silently corrupts
the entire statistical-factor lane rather than crashing.

## Non-blocking notes

- **[strategies/run_residual_reversion.py:618]** `except Exception: pass` still falls back to
  `oos_full` when the trimmed drop-top-3 backtest errors, rendering `drop3 == full` instead of
  surfacing the failure (carried from round 4/5).
- **[strategies/robustness.py:212]** `remove_top_pnl_contributors` sums `lagged_weight × return`
  gross of cost allocation despite the "allocated costs" docstring (carried, pre-existing).
- PCA fitting uses `train_slice.notna().all(axis=0)` (full 60 finite) and never applies
  `min_obs`, so it is stricter than the OLS 48/60 tolerance — a design note, not the defect above.

## Checks run

```
$ python -m pytest -q -p no:cacheprovider tests/strategies tests/ml
175 passed, 17616 warnings in 122.29s

$ PYTHONPATH=<temp>/sitecustomize python -m pytest -q -p no:cacheprovider tests/strategies tests/ml
   (sitecustomize sets pyspark/pyspark.sql/pyspark.sql.functions/pyspark.sql.types = None)
175 passed, 17616 warnings in 122.10s

# probe: PCA day-t NaN/huge leaves t-dated loadings identical -> PASS (see finding 1)
# probe: AST guard on real source empty; on added unused compute_* -> flagged -> PASS
# probe: K outside [10,15] raises; K=10/15 succeed; config 0/20 raise -> PASS
# probe: NaN gap in training window -> residual column shift (S00 gets S01's residual, S07 NaN) -> FAIL
```

(The warning count differs from MiMo's 34 only because this environment is Python 3.14, where
`pytest_asyncio`/pandas emit extra DeprecationWarnings; they are unrelated to the code under review.)
===VERDICT END===
