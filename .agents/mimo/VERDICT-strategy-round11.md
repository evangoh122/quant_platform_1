# VERDICT: strategy-round11 — MiMo
**Status:** APPROVED
**Round:** 11

## Blocking findings
(none)

## Non-blocking notes
- The fix is minimal and surgical: one new key in `build_signals` return dict, four caller sites updated to use it.
- The masked `returns` key is preserved for signal construction (regressions, industry factor) — correct separation of concerns.
- Both keys are explicit (`returns` vs `valuation_returns`) so they cannot be confused again.

## Checks run
- `python3 -m pytest -q tests/strategies tests/ml` → 89 passed
- `python3 -m pytest -q tests/strategies tests/ml -p no:pyspark` → 89 passed
- `test_exit_day_pnl_includes_held_name_return` → passes (demonstrates masked returns drop exit-day P&L, unmasked returns include it)
- `test_missing_close_contributes_zero_not_fabricated` → passes (NaN return correctly contributes 0)
- `test_signals_unchanged_by_valuation_returns_fix` → passes (s-scores and positions identical; `valuation_returns` key present and unmasked)
- Verified test_signals_unchanged_by_valuation_returns_fix FAILS on HEAD (no `valuation_returns` key)