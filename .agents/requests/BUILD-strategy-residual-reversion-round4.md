# BUILD-REQUEST: strategy-residual-reversion — ROUND 4

**Builder:** MiMo · **Checkers:** Claude, then DeepSeek
Read `.agents/deepseek/VERDICT-strategy-check.md`. DeepSeek verified the PIT universe, industry
factors, ADV cap and walk-forward as correct — keep them. One blocking defect plus doc fixes.

## Blocking: the min-history gate is disabled
`gold/06_gold_tradable_universe.sql:75-78` computes `history` as `COUNT(*) OVER (...)` over the dense
`symbol × market_date` grid. Pre-listing rows have `dollar_volume IS NULL` and `COUNT(*)` counts them,
so every symbol appears to have the full calendar's history. Measured by DeepSeek: **58 of 585
universe symbols had < 252 of their own sessions; SPCH, DJT, EXE, ICCT, CRWV entered after only 5.**

Fix: count the symbol's own trading sessions strictly before `t`:
`COUNT(dollar_volume) OVER (PARTITION BY symbol ORDER BY event_date ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)`.

## Then
1. Rebuild `gold_tradable_universe` (the MERGE now has `WHEN NOT MATCHED BY SOURCE THEN DELETE`).
   Run from **WSL**: `wsl -e bash -lc "cd /home/jianj/code/qp1-strat2 && python3 ..."` — Windows
   PowerShell has no Databricks config. Paste: rows removed/added, members/day min/median/max, and a
   query proving **0** universe members have < 252 own sessions before their membership date.
2. Re-run the backtest and write **`strategies/results/residual_reversion_r3.md`** (keep r1/r2).
   Its "what changed" section must state that r2 ran without an effective min-history gate.
3. `strategies/run_residual_reversion.py:298` hardcodes the date range in the results header —
   derive it from the data.
4. Add a test for the history gate that fails if it counts NULL/pre-listing rows.

If you cannot execute against Databricks, say so and stop — do not regenerate results.
Edit only `gold/06_gold_tradable_universe.sql`, `strategies/`, `tests/strategies/`. LF line endings.
**Commit your work.** Write `.agents/mimo/VERDICT-strategy-residual-reversion-round4.md`.
