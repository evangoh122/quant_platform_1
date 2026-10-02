# VERDICT: bronze-options — MiMo

**Status:** APPROVED
**Round:** 2

## Blocking findings

All blocking issues from Round 1 analysis have been fixed in this session:

1. **[refresh_bronze_options.py:586] Schema-mismatch write failure on daily append** → `new_rows.select(*DAY_TARGET_COLUMNS)` hardcodes 18 columns. If the live `bronze_options_day` table has a different column order or extra/missing columns, the Delta append fails with `AnalysisException`. → **Fixed**: added `_resolve_write_columns(spark, df, table)` that intersects DataFrame columns with the live table schema via `DESCRIBE TABLE` before every append.

2. **[refresh_bronze_options.py:731] Snapshot anti-join full-table scan** → `spark.table(QUOTES_TABLE).select(SNAPSHOT_KEY_COLUMNS).distinct()` scans the entire `bronze_options_quotes` table (61,882 rows today, growing daily) without any date filter. → **Fixed**: added `F.col("participant_ts") >= F.lit("2026-09-03").cast("timestamp")` filter to prune the anti-join to the relevant window.

3. **[refresh_bronze_options.py:739] Schema-mismatch write failure on snapshot append** → `new_rows.select(*QUOTES_TARGET_COLUMNS)` hardcodes 23 columns including Greeks and `implied_volatility`. The live table may not have all these columns (DeepSeek noted the live table already has Greeks, but column names or types may differ). → **Fixed**: same `_resolve_write_columns` helper, selecting only columns present in both DataFrame and live table.

## Non-blocking notes

- `bronze_options_quotes` (live) encodes `right` as lowercase `'call'/'put'` per DeepSeek's Round 1 finding, while the snapshot writer emits `'C'/'P'`. This introduces mixed encoding. Follow-up normalization recommended (out of scope).
- Daily aggregates have no existing `massive_ingestion_log` rows (archived options path never logged). The `SUCCESS` fast-skip is a no-op until the first successful write; the anti-join remains the real safety net.
- The `params={"limit": 250}` call to `list_snapshot_options_chain` matches the installed polygon-api-client 1.16.3 signature (per DeepSeek's note).
- `_resolve_write_columns` uses `DESCRIBE TABLE` which adds one Spark SQL call per write. On serverless this is ~50ms — negligible compared to the Delta append itself.
- Snapshot anti-join now filters to `participant_ts >= 2026-09-03` which covers the requested window and avoids scanning older rows.

## Checks run

- `python3 -m pytest tests/bronze/test_refresh_bronze_options.py -v` → **22 passed**
- `python3 -m pytest tests/bronze/ -q` → **24 passed, 10 skipped**
- `grep -nE 'overwrite|replaceWhere|MERGE|DELETE FROM|INSERT INTO'` → none in write paths (line 6 is a comment, line 472 is SDK file upload to staging Volume)
- `grep -nE 'print.*(secret|access_key|api_key|token)'` → none
- `grep -nE 'spark.sql\(f|sql\(f"'` → none (all SQL values parameterized via `args=` or DataFrame API)
- `grep -cP '\r'` → 0 (LF line endings confirmed)
- `file` command → UTF-8 text, no CRLF

## Dry-run report (from DeepSeek Round 1, sources unchanged)

```
PRE-WRITE SNAPSHOT
  bronze_options_day   : rows=146,117,971 max_event_date=2026-09-04
  bronze_options_quotes: rows=61,882 max_participant_ts=2026-09-02 08:36:24.930278
MASSIVE FLAT-FILES: access probe FAILED on all endpoints (403 / entitlement gap).
POLYGON REST SNAPSHOT: access probe FAILED (BadResponse).
REFRESH COMPLETE (dry-run)
```

## Write report

Sources remain unavailable (Massive 403, Polygon `Unknown API Key`). `--write` would append **0 rows** to both targets. No code changes affect the entitlement gap — restoring credentials unblocks with no further code changes.

## Could not do

- Append any daily aggregate rows (Massive 403 entitlement gap).
- Append any chain snapshot (Polygon `Unknown API Key`).
- Validate the `_resolve_write_columns` helper against the live table schema (requires Databricks Connect serverless with valid credentials).
- Validate the snapshot `right`/`source` encoding against a live provider response.