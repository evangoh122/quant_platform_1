# VERDICT: strategy-round9 — MiMo
**Status:** APPROVED
**Round:** 9

## Blocking findings
- None.

## Changes made

### 1. pandas 3 read-only array guard
- `strategies/backtest.py:84` — `weights.copy().to_numpy(dtype=float)` → `weights.to_numpy(dtype=float, copy=True)`. The `out` array is written to at line 124 (`out[i] = ...`). Under pandas 3 copy-on-write, `.to_numpy()` can return a read-only view; `copy=True` guarantees a writeable copy on both pandas 2 and 3.
- Audited all `.to_numpy()` / `.values` in `strategies/`, `ml/`, `tests/`: only this one site mutates the returned array in-place. All other call sites either pass to read-only functions or assign via pandas `.loc[]` (which handles its own copy semantics).
- Added `test_cap_weight_changes_with_read_only_input` in `tests/strategies/test_backtest.py` — makes input arrays read-only via `setflags(write=False)` and asserts the function succeeds. This reproduces pandas-3 behaviour on pandas 2.

### 2. ADV forward-fill before zero-fill
- `strategies/run_residual_reversion.py:193` — removed `.fillna(0.0)` from the ADV reindex in `run_one`. The ADV frame now preserves NaN for names that leave the universe.
- `strategies/backtest.py:337` — removed `.fillna(0.0)` from the ADV reindex in `run_backtest`. `cap_weight_changes_by_adv` already does its own `ffill()` + `fillna(0)` internally, so pre-filling with 0 defeated the forward-fill for exited names.
- The second ADV alignment (line 345-346, for cost computation) retains `fillna(0.0)` since `compute_costs` treats NaN/0 identically (100% participation) but explicit 0 is cleaner.

### 3. Test path resolution
- `tests/strategies/test_universe.py:238` — `pathlib.Path("gold/07_gold_regime_features.sql")` → `pathlib.Path(__file__).resolve().parents[2] / "gold" / "07_gold_regime_features.sql"`.
- `tests/lakebase/test_migrations.py:140` — `Path("db/migrations")` → `Path(__file__).resolve().parents[2] / "db" / "migrations"`.

### 4. CHANGELOG[8]
- Added to `strategies/run_residual_reversion.py` CHANGELOG dict with entries for all three fixes.

## Non-blocking notes
- Other `.to_numpy()` call sites in `ml/` and `strategies/` are safe: they either produce fresh arrays (e.g. `rolling().std()`) or the returned arrays are only read, never written to. No defensive `copy=True` added to those — unnecessary copies would penalise hot paths for zero benefit.
- pandas 3 is not added to CI (would require a separate matrix entry). The read-only test (`setflags(write=False)`) serves as the guard.

## Checks run
- `python3 -m pytest -q tests/strategies tests/ml` (repo root) → 84 passed
- `PYSPARK_PYTHON="" python3 -m pytest -q tests/strategies tests/ml` (pyspark hidden) → 84 passed
- `cd tests && python3 -m pytest -q strategies ml` (cwd=test) → 84 passed
- LF line endings verified on all modified files (`file` check — no CRLF)
- No scratch files left in tree
- `git log --oneline -3` → commit `4ba0226` on `slice/strategy-residual-reversion`