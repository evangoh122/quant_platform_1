# BUILD-REQUEST: strategy-residual-reversion — ROUND 3

**Builder:** MiMo · **Checkers:** Claude, then DeepSeek

## Round 2 claimed fix #1 but it never ran — measured by the coordinator
- `gold/06_gold_tradable_universe.sql` **fails to execute**:
  `[UNRESOLVED_COLUMN.WITH_SUGGESTION] ... event_date cannot be resolved. Did you mean ... market_date`
  (line 15 of the MERGE statement). The MERGE is atomic, so the live table is still the
  **round-1 (look-ahead) universe**: `DESCRIBE HISTORY` shows only versions 0 (CREATE) and 1 (round-1 MERGE).
- `strategies/run_residual_reversion.py` reads `gold_tradable_universe` (lines 71, 82), so
  **`residual_reversion_r2.md` does not include fix #1**, although its "What changed" table says it does.
- The coordinator already added `WHEN NOT MATCHED BY SOURCE THEN DELETE` to the MERGE (committed) so
  stale members are removed on rebuild. Keep it.

## Do
1. Fix the SQL so it runs. Test it **actually executes** against the live schema
   (databricks-connect serverless, run from WSL: `wsl -e bash -lc "cd <worktree> && python3 ..."`;
   Windows PowerShell has no Databricks config).
2. Report before/after universe: rows, members per day (min/median/max), and how many
   (trade_date, symbol) memberships were removed/added vs the round-1 table.
3. Re-run the backtest end to end and **regenerate `residual_reversion_r2.md`** so every number
   reflects all four fixes. Do not claim a fix whose code did not run.

If you cannot execute against Databricks, **say so plainly and stop** — do not regenerate results.
Edit only `gold/06_gold_tradable_universe.sql`, `strategies/`, `tests/strategies/`.
LF line endings. **Commit your work.** Write `.agents/mimo/VERDICT-strategy-residual-reversion-round3.md`.
