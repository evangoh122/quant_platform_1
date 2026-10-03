===VERDICT START===
# VERDICT: strategy-robustness-check7 — DeepSeek
**Status:** APPROVED
**Round:** 13 (robustness round-7 re-check)

Re-checked MiMo round 7 (commit `459eb4d`) at HEAD `5f07e35` on
`slice/strategy-robustness`. Read-only; all scratch in `/tmp/ds_check7`, nothing in
the worktree. Nothing committed or pushed.

## Round-7 verify items — all PASS (proofs)

### 1. PCA residual per-symbol alignment — FIXED
- `strategies/residual_reversion.py:399` now writes `residual.loc[dates[t], sym]`
  (label-based) instead of `residual.iloc[t, j]`. `residual` (`:313`) is keyed by the
  full symbol list; `sym` is `valid_syms[j]`, so the write is correctly aligned.
- **Independent probe** (my own reference implementation written from scratch, same
  math: Ledoit-Wolf + `eigh`, per-symbol `lstsq` on factor scores, projection):
  - NaN gap in `S00` (first column): 800 cells, **0 mismatches**; `S00` residual is NaN.
  - NaN gap in `S04` (middle column): 800 cells, **0 mismatches**.
  - NaN gaps in `S00` and `S04`: 800 cells, **0 mismatches**.
  Every residual value matches the independent per-symbol reference at `atol=1e-9`.

### 2. Positional-write audit of the PCA path — CLEAN
- The only DataFrame column write in `compute_pca_residuals` is the fixed
  `residual.loc[dates[t], sym]` (line 399). Remaining `.iloc` uses in
  `residual_reversion.py` are row-slices (`returns.iloc[t-window:t]`, `returns.iloc[t]`,
  `returns.iloc[t][valid_syms]`, lines 319/321/368) — time alignment, not column
  writes. Every remaining `j` index (`train_std[:, j]`, `day_t_sym[j]`, `scales[j]`,
  `means[j]`, lines 381/390/398-399) indexes numpy arrays already subsetted to
  `valid_syms`, so `j` ↔ `valid_syms[j]` ↔ `sym` is consistent.
- `sigma`/`s_score` are derived column-wise (`.apply`, `.rolling`) from the now-correct
  `residual`, so they cannot be misaligned.

### 3. Drop-top-3 failure surfacing — FIXED
- `run_residual_reversion.py:596,616-624` records `drop3_failed = "drop3 failed:
  <ExcType>"` on exception, sets `oos_sharpe_drop3=None`, and stores `drop3_error`.
- `robustness.py:734-744` renders `n/a` for a missing `oos_sharpe_drop3` and appends the
  note column.
- **Probe:** report contains `n/a` and `drop3 failed: ValueError` for the failed fold,
  and `0.470` for the successful fold. Drop3 is never consumed by `evaluate_gates`
  (gates read `_variant_metrics`, not `oos_sharpe_drop3`), so the "exclude from gates"
  requirement holds.

### 4. PCA fit-tolerance choice documented — YES
- `residual_reversion.py:285-292` documents that PCA requires a full window per symbol
  (`train_slice.notna().all`) because Ledoit-Wolf needs complete observations, and that
  `min_obs` controls only the trailing sigma. Matches the code (`:325`, `:406`).

## Full pass — every report quantity (re-verified post-fix)

| Report quantity | Verdict |
|---|---|
| Factor-model net/IS/OOS Sharpe, OOS/IS, DSR (OLS + PCA) | **PASS** |
| Cost stress 2×/3× (commission/spread/slippage/borrow ×1 once; gross/participation unchanged) | **PASS** |
| Universe stress 200/500 (dense-grid `screen_universe`) | **PASS** |
| Parameter perturbation ±20% | **PASS** |
| Top-3 P&L contributor removal (registry variant; gross-P&L ranking now honestly documented) | **PASS** |
| Per-fold drop-top-3 (train-window realised `trade_returns` P&L; net-vs-net OOS; failure surfacing) | **PASS** |
| Walk-forward folds (purged validation folds) | **PASS** |
| Exposures (dollar `Σw/gross`, beta `Σw·β/gross`, sector `max|net|`) | **PASS** |
| Turnover / capacity / margin bps | **PASS** |
| Rank IC (forward residual sum t+1..t+H; HAC lag H-1; n & eff. n disclosed) | **PASS** |
| Gate summary + honest trial count (fingerprint-dedup) | **PASS** |

No quantity is placeholder-computed; the single check6 blocker (PCA column shift) is
resolved and does not corrupt the statistical-factor lane.

## Non-blocking notes

- **[strategies/robustness.py:740]** A *successful* drop3 fold stores
  `"drop3_error": None`, so `fr.get("drop3_error", "")` returns `None` and the note
  column renders the literal string `None` (probe: `| 0 | A | 0.550 | 0.470 | None |`).
  Cosmetic only — the value is correct; suggest `fr.get("drop3_error") or ""`.
- **[strategies/robustness.py:211]** Inline comment still says "Per-symbol total
  realized net P&L contribution" while the (now-honest) docstring says gross P&L. The
  comment lags the docstring fix.
- **[tests/strategies/test_robustness_round7.py]** No dedicated test asserts the drop3
  failure-surfacing branch (BUILD round-7 item 2 said "Test it"); the 3 new tests cover
  PCA only. Non-blocking — the render path is covered by my probe and existing
  round-3 report tests.

## Checks run

```
$ python3 -m pytest -q -p no:cacheprovider tests/strategies tests/ml
178 passed, 34 warnings in 127.92s

$ PYTHONPATH=/tmp/sitecustomize python3 -m pytest -q -p no:cacheprovider tests/strategies tests/ml
   (sitecustomize sets pyspark/pyspark.sql/pyspark.sql.functions/pyspark.sql.types -> None/raises)
178 passed, 34 warnings in 104.67s
   (verified: ambient pyspark 4.4.0.dev0 present; hidden run blocks import -> suite does
    not depend on ambient env)

# probe: NaN gap in S00 / S04 / both -> 800 cells each, 0 mismatches vs independent ref -> PASS
# probe: column-permutation invariance under 5% NaN gaps -> PASS
# probe: drop3 report shows 'n/a' + failure note + numeric value -> PASS
```
===VERDICT END===
