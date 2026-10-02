# VERDICT: bronze-equities — MiMo

**Status:** CHANGES_REQUESTED
**Round:** 1

## Blocking findings

- [notebooks/refresh_bronze_equities.py] Massive S3 credentials return 403 on ALL list and GET operations for all years (2020-2026). Dry-run completes with 0 files found. Cannot proceed to `--write` until entitlement is restored. → Both `files.massive.com` and `files.polygon.io` endpoints return 403 for listing and HEAD/GET. The subscription may have expired or keys were rotated without updating the Databricks secret scope `evangoh_capstone`.

## Non-blocking notes

- Pre-existing data quality issue: `bronze_ohlcv` contains 5,746,090 duplicate groups (5,752,271 excess rows). These are "day" timespan bars (102,395 rows) loaded by the archived REST API Option A into the same table as minute bars, causing key collisions. The anti-join in this refresh correctly prevents adding new duplicates, but the existing ones need a separate cleanup pass.
- `bronze_ohlcv_day` is clean: 0 duplicates found.
- Performance optimization applied: anti-join key set is materialized via `count()` once per dataset to warm the Delta cache, avoiding repeated full table scans per file iteration.
- S3 client configured with explicit timeouts (connect=10s, read=120s) and3-attempt retry with standard backoff mode. Library defaults replaced.
- `unpersist()` is not supported on Databricks serverless compute — removed the call. Delta manages cache lifecycle automatically on serverless.
- Unit tests: 10/10 pass (parsing helpers, key filtering, universe filtering, date derivation).

## Checks run

- `python -m pytest tests/bronze/test_refresh_bronze_equities.py -v` → 10 passed, 0 failed
- `python run_equities.py --mode dry-run` → completed, 0 files found (S3 403 entitlement gap)
- Verification queries against live tables:
  - `bronze_ohlcv`: 72,678,354 rows, max_event_ts=2026-09-02 23:59:00
  - `bronze_ohlcv_day`: 12,993,270 rows, max_event_ts=2026-09-04 04:00:00
  - Duplicate check on `bronze_ohlcv` window 2026-09-01+: returns "day" timespan duplicates (pre-existing, not from this refresh)
  - Duplicate check on `bronze_ohlcv_day` window 2026-09-01+: 0 duplicates
  - `massive_ingestion_log`: 2,346 SUCCESS / 43 FAILED / 1 CANCELLED
  - `massive_daily_ingestion_log`: 1,173 SUCCESS / 0 FAILED

## What must happen before this lane can write

1. Restore Massive S3 entitlement — verify credentials in scope `evangoh_capstone` have `s3:ListBucket` and `s3:GetObject` on bucket `flatfiles`.
2. Re-run `--dry-run` to confirm file discovery and candidate counts.
3. Review and approve dry-run report.
4. Run `--write` and verification queries.
5. Address pre-existing 5.7M duplicate groups in `bronze_ohlcv` as a separate cleanup task (not in this lane's scope).