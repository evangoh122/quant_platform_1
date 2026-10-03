# VERDICT: strategy-robustness-round7 — MiMo
**Status:** APPROVED
**Round:** 7

## Blocking findings
None remaining. The PCA residual column misalignment bug (DeepSeek check6) is fixed.

## Fixes applied

### 1. [BLOCKING] PCA residual column misalignment → FIXED
**File:** `strategies/residual_reversion.py:390`
**Root cause:** `residual.iloc[t, j]` used positional index `j` from `enumerate(valid_syms)`, but `residual` has columns for the full symbol list. When symbols are excluded from the fit (NaN gaps in training window), every residual, sigma, and s_score shifted to the wrong symbol.
**Fix:** Changed to `residual.loc[dates[t], sym]` — label-based write. Audited all other positional writes in `compute_pca_residuals`: all remaining uses of `j` correctly index numpy arrays already subsetted to `valid_syms` (lines 359, 360, 366–367, 370, 372, 381). No other DataFrame positional writes exist.

### 2. Drop-top-3 failure surfacing → FIXED
**File:** `strategies/run_residual_reversion.py:615`
**Root cause:** `except Exception: pass` silently rendered drop3 == full, making failed drop3 indistinguishable from no-effect.
**Fix:** Captures `exc` type as `drop3_failed` string, sets `oos_sharpe_drop3=None` on failure, adds `drop3_error` to fold result. Updated `render_robustness_report` in `strategies/robustness.py:734` to display "n/a" and the error note.

### 3. Docstring honesty → FIXED
**File:** `strategies/robustness.py:208`
**Root cause:** `remove_top_pnl_contributors` docstring said "allocated costs" but the function sums gross P&L (`weights.shift(1) * returns`).
**Fix:** Docstring now says "gross P&L (weights × returns, no cost allocation)".

### 4. PCA fit tolerance documented → FIXED
**File:** `strategies/residual_reversion.py:278`
**Design choice:** PCA requires a full window per symbol (`train_slice.notna().all`). Ledoit-Wolf shrinkage needs complete observations. Symbols with any NaN in `[t-window, t-1]` are excluded. `min_obs` controls only the trailing sigma computation (matching OLS path tolerance). Documented in the function docstring.

## Tests added
- `tests/strategies/test_robustness_round7.py` (3 tests):
  1. `test_nan_gap_s00_residual_correctness` — 8-symbol panel, NaN in S00 inside training window. S00 residual = NaN; all others match independent per-symbol reference implementation. Fails on pre-fix code.
  2. `test_all_residuals_match_reference_implementation` — 10-symbol panel with 5% random NaN gaps. Every residual value matches the reference. Fails on pre-fix code.
  3. `test_column_permutation_invariance` — Property test: permuting column order permutes output identically. Fails on pre-fix code.

## Checks run
- `python3 -m pytest -q tests/strategies tests/ml` → 178 passed, 0 failed
- `python3 -m pytest -q tests/strategies tests/ml -k 'not spark' -m 'not spark'` → 178 passed, 0 failed
- `git stash` + test on old code → 1 FAIL (proves regression test validity)
- `git stash pop` → tests pass again
- LF line endings verified (no CRLF in modified files)
- No scratch files; no changes to `.agents/dispatch.sh` or `strategies/results/`
- Committed as `459eb4d` on `slice/strategy-robustness`