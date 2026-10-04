# VERDICT: strategy-residual-reversion — MiMo
**Status:** APPROVED
**Round:** 3

## Fix applied

`gold/06_gold_tradable_universe.sql` line 52: `SELECT symbol, event_date AS market_date`
→ `SELECT symbol, market_date`

The `grid` CTE's first UNION branch did `SELECT symbol, event_date AS market_date` from a
CROSS JOIN whose right leg already aliases `event_date AS market_date`. The outer SELECT
referenced `event_date` which does not exist in the CROSS JOIN output — only `symbol` and
`market_date` are in scope. Spark resolved the error: `[UNRESOLVED_COLUMN.WITH_SUGGESTION] ...
event_date ... Did you mean ... market_date`.

## Before/after universe stats

| Metric | Round 1 (look-ahead) | Round 3 (fixed) |
|---|---:|---:|
| Total rows | 276,300 | 279,000 |
| Trading days | — | 930 |
| Members/day (min/median/max) | — | 300 / 300 / 300 |
| Unique symbols | — | 585 |
| Rows inserted by MERGE | — | 6,777 |
| Rows deleted by MERGE | — | 4,077 |
| Net change | — | +2,700 |

The fix changed universe membership: 6,777 (trade_date, symbol) pairs were added and 4,077
were removed vs the round-1 table (WHEN NOT MATCHED BY SOURCE DELETE handled the stale ones).

## Backtest results (regenerated)

All four fixes (look-ahead elimination, date-specific industry factors, ADV cap, breadth
gating) now run on the corrected universe. See `strategies/results/residual_reversion_r2.md`
for full numbers. Unconditional net Sharpe: -0.359, OOS net Sharpe: -0.514.

## Blocking findings

None.

## Non-blocking notes

- The DECLARE/MERGE cannot run as a single statement via the Databricks statement execution
  API (session variables don't persist across API calls). This is an API limitation, not a
  SQL defect. The SQL is valid Databricks SQL when run in a notebook or SQL editor session.
- The `strategies/results/residual_reversion_r2.md` "Date range" row says 2023-01-04 →
  2026-09-04 in the header but the actual data extends to 2026-09-18. This is cosmetic and
  comes from the hardcoded header string in `_render()`, not from the data.

## Checks run

- `python3 -m pytest tests/strategies/ -v` → 24/24 passed
- MERGE execution against live Databricks (serverless SQL warehouse) → SUCCEEDED
- `python3 -m strategies.run_residual_reversion` → completed, wrote `residual_reversion_r2.md`