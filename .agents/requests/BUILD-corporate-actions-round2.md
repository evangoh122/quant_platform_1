# BUILD: corporate actions round 2 (MiMo)

> **IMPLEMENT NOW.** No confirmation questions. Commit when done. NEVER delete or weaken existing
> tests.

DeepSeek (`.agents/deepseek/VERDICT-corporate-actions.md`, read it fully), 3 blocking issues:

1. **The daily `information_available_ts` is wrong** (`silver/08_silver_ohlcv_day_adjusted.sql:~338-341`).
   It uses 16:00 instead of 16:30, AND `from_utc_timestamp` (the wrong direction). It must be
   `to_utc_timestamp(to_timestamp(concat(cast(event_date AS STRING),' 16:30:00')), 'America/New_York')`.
   2022-06-06 → 20:30 UTC (EDT); 2022-12-05 → 21:30 UTC (EST).
   Test: assert both DST cases. A SQL-text test is not enough; evaluate the expression in a
   pyspark-free reference (Python `zoneinfo`) AND assert the SQL uses `to_utc_timestamp` with
   16:30.
2. **`data_quality_breaks` MERGE `INSERT *` column mismatch** (`:~296`, a 14-column source vs a
   16-column target). Use an explicit column list
   `INSERT (col1, …) VALUES (src.col1, …)`, with `reviewed_by`/`reviewed_ts` NULL. Do the same for
   every MERGE in this file. Test: parse the target DDL and assert the INSERT lists every target
   column exactly once.
3. **The ingest notebook ignores CLI flags** (`notebooks/refresh_bronze_corporate_actions.py:~135-176`).
   `resources/jobs.yml` and the runbook pass `--mode write --run-id … --delay-seconds …
   --symbol-start/--symbol-end`, but only `dbutils.widgets` is read, so `--mode write` silently runs
   dry-run.
   - Add `argparse` in `main()`: args first, falling back to widgets for interactive use.
   - An unknown flag raises.
   - Test: `--mode write` sets write mode; omitting it keeps dry-run.
   - Also check the other refresh notebooks follow the same pattern; don't edit them, just note
     them in the verdict.

Fix any quick factual non-blocking notes too. Run `python3 -m pytest -q -p no:cacheprovider` and the
full suite with `--ignore=tests/lakebase`, both with pyspark hidden too. LF line endings only. Don't
touch `.agents/dispatch.sh`. Write `.agents/mimo/VERDICT-corporate-actions-round2.md`.
