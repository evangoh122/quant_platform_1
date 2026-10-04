# BUILD: strategy round 9, CI + CodeRabbit findings on PR #16 (MiMo)

Three issues, each with a test that FAILS on the current HEAD (prove it in /tmp).

1. **[Blocking, CI] pandas 3 read-only arrays.** CI runs pandas 3.x; locally it's 2.3. In CI,
   `strategies/backtest.py:124` raises `ValueError: assignment destination is read-only`, because
   `.to_numpy()` can return a read-only view under copy-on-write. Audit every
   `.to_numpy(...)` / `.values` that is later written to, in `strategies/`, `ml/` and `tests/`, and
   use `.to_numpy(copy=True)` / `np.array(..., copy=True)`.
   - Test: build the arrays from a DataFrame and assert the function works when the input arrays are
     made read-only (`arr.setflags(write=False)`). This reproduces the pandas-3 behaviour on pandas 2.
   - Also add pandas 3 to CI coverage if cheap. Otherwise state in the verdict that the read-only
     test is the guard.
2. **[Major, CodeRabbit] ADV zero-filled before forward-fill.** `run_one` fills missing ADV with 0
   before `cap_weight_changes_by_adv` and `compute_costs`. So when a held name leaves the universe:
   - the cap helper can't forward-fill its last known ADV;
   - the exit is costed at 100% participation, roughly 200 bps slippage.

   Fix: build the ADV frame once, with a per-symbol forward-fill of past-only values, then apply
   `fillna(0)` only for names with NO known ADV. Pass the same frame to the cap and the costs.
   Test: a name held, then dropped from the universe. The exit cost uses its last known ADV, not 100%
   participation.
3. **[Minor, CodeRabbit] Test path.** In `tests/strategies/test_universe.py:~238`, resolve the SQL
   path from `__file__` (`Path(__file__).resolve().parents[2] / "gold" / ...`). Do the same for any
   other test that reads repo files by relative path.

Add `CHANGELOG[8]`. Run:
- `python3 -m pytest -q tests/strategies tests/ml`;
- the same suite with pyspark hidden;
- the same suite from inside `tests/` (cwd test).

LF line endings only. Don't touch `.agents/dispatch.sh` or `strategies/results/`. Leave no scratch
files. Commit with a descriptive message. Write `.agents/mimo/VERDICT-strategy-round9.md`. Claude
reruns live as r8 afterwards.
