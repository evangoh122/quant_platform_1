# VERDICT: strategy-residual-reversion-round4 — MiMo
**Status:** APPROVED
**Round:** 4

## Changes made
1. **`gold/06_gold_tradable_universe.sql:75`** — `COUNT(*)` → `COUNT(dollar_volume)` so the history gate counts only the symbol's own trading sessions (non-NULL dollar_volume), not pre-listing NULL rows in the dense grid.
2. **`strategies/universe.py:43`** — `s.rolling(1).count().cumsum()` → `s.notna().cumsum()` — same bug in the pandas reference; rolling count on a single non-null element counts all rows, not just non-null.
3. **`strategies/run_residual_reversion.py:298`** — Date range now derived from `dates[0]` and `dates[-1]` instead of hardcoded "2023-01-04 → 2026-09-04".
4. **`strategies/run_residual_reversion.py:205`** — Default output changed to `residual_reversion_r3.md`; "what changed" section documents the min-history gate fix.
5. **`tests/strategies/test_universe.py`** — New `test_history_gate_counts_own_sessions_not_grid_rows`: creates a late-lister (LATE) with 50 own sessions in a 400-day calendar. Would pass under `COUNT(*)` (grid rows ≥ 252) but correctly fails under `COUNT(dollar_volume)`. Verifies LATE is excluded with `min_history=252`.

## Databricks verification (live)
- Rebuilt `gold_tradable_universe`: 281,700 rows, 939 days (2023-01-04 → 2026-10-01), 556 symbols, 300/day (min/median/max all 300).
- **0 universe members have < 252 own trading sessions before their first membership date** — PASS. The 58 symbols DeepSeek flagged (SPCH, DJT, EXE, ICCT, CRWV, etc.) are no longer admitted early.

## Backtest re-run
- `strategies/results/residual_reversion_r3.md` written with live data.
- Net Sharpe: -0.335 (was -0.359 in r2 with the broken gate).
- Gated (NARROW) net Sharpe: 0.330 (was 0.007 in r2).
- Walk-forward OOS Sharpe: -0.411 (was -0.514 in r2).
- Date range correctly shows 2023-01-04 → 2026-10-01 (derived from data).

## Non-blocking notes
- The DeepSeek non-blocking note about `_rolling_lagged_sum` imputing NaN as 0 in beta cross-products (`strategies/residual_reversion.py:107`) was not addressed — it is pre-existing, narrower, and does not reintroduce cross-symbol leakage. Not in scope for this round.

## Checks run
- `python3 -m pytest tests/strategies -q` → **25 passed**, 16 warnings
- Databricks live rebuild + verification query → **0 symbols < 252 sessions** (PASS)
- Backtest re-run → `strategies/results/residual_reversion_r3.md` written (PASS)