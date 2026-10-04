# BUILD residual reversion round 12 — run on Massive split-adjusted prices (builder: MiMo; checker: DeepSeek; reviewer: Codex; final: Claude)

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/strategy-residual-reversion. Commit after each item, descriptive messages.
NEVER delete or weaken existing tests. You cannot reach Databricks; Claude runs the live rerun after this round.

## Context (verified live by Claude 2026-10-04)
bronze_ohlcv_day is NOT split-adjusted (AMZN 2022-06-06 shows −94.9%; 237 jumps ≥40% in the universe), which contaminates the r9 results.
`bootcamp_students.evangoh_capstone.silver_ohlcv_day_adjusted` now exists (639,369 rows; Massive splits): columns include symbol, event_date,
open/high/low/close (raw), adj_open/adj_high/adj_low/adj_close/adj_vwap/adj_volume, cumulative_split_ratio, price_adjustment_factor, return_1d
(NULL on masked break days), information_available_ts. AMZN adjusted return on 2022-06-06 = +1.99%.
`data_quality_breaks` (237 rows): classification SPLIT_EXPLAINED (63, is_masked=false) and UNEXPLAINED_PENDING (174, is_masked=true — ticker reuse
such as META 2022-06-09 ×14.9, renames like BNY, collapses like FRC, leveraged ETFs). DDL for reference:
`git show slice/corporate-actions:silver/08_silver_ohlcv_day_adjusted.sql`.

## Items
1. Price source config (strategies/run_residual_reversion.py fetch_data ~:79, strategies/config.yaml): `price_table` (default
   `silver_ohlcv_day_adjusted`) + CLI `--price-table`. For the adjusted table select `adj_close AS close`; for bronze keep `close` and log a loud
   WARNING that prices are unadjusted. Include the source in the results report header.
2. Masked breaks: returns on (symbol, event_date) where silver `return_1d IS NULL` because of a masked break (or where data_quality_breaks.is_masked)
   must not be used as signal inputs or P&L: fetch the mask and set that day's return to NaN in the returns frame used by signals AND valuation
   (document the choice; positions held across a masked day earn 0 that day — state it in the report limitations).
3. Tests: generated SQL reads the configured table and maps adj_close; bronze path logs the warning; a masked break day yields NaN return and no
   signal/P&L contribution (synthetic panel with a ×15 jump flagged masked → no trade triggered by it). Mutation (copy via
   `git archive HEAD | tar -x -C /tmp/<dir>`, paste output): ignore the mask → test FAILS.
4. Report: results file name for the rerun is strategies/results/residual_reversion_r10.md; keep r9 but mark it SUPERSEDED (unadjusted prices) at
   its top. README/docs mention the adjusted source.
Acceptance: python -m pytest -q tests/strategies tests/ml all pass (also with the pyspark-hidden shim if used before).
.agents/mimo/VERDICT-strategy-residual-reversion-round12.md. Commit everything.
