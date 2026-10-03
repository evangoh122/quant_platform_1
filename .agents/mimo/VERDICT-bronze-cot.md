# VERDICT: bronze-cot — MiMo

**Status:** APPROVED
**Round:** 1

## Blocking findings

None.

## Non-blocking notes

- `compute_release_ts()` is defined in the notebook but no longer called by `to_bronze()` (which now uses Spark SQL `F.to_utc_timestamp` matching the archive pattern). The function and its tests remain as a standalone helper — harmless but dead code for the current flow.
- Pandas 3.0 `ChainedAssignmentError` FutureWarnings appear at runtime. These are cosmetic and don't affect correctness; switching to `.loc` assignment is a follow-up cleanup.
- The latest CFTC report in the 2026 annual file is 2026-09-22. The next report (2026-09-29) would release ~2026-10-05, beyond the 2026-10-03 window. This is expected — COT data may legitimately lag behind the end date.

## Checks run

- `python -m pytest tests/bronze/test_refresh_bronze_cot.py -v` → 32 passed, 0 failed
- `python notebooks/refresh_bronze_cot.py --dry-run` → DRY_RUN, 292 candidates each (com_fin, fut_fin), 0 conflicts
- `python notebooks/refresh_bronze_cot.py --write` → OK, com_fin 15437→15729 (+292), fut_fin 15427→15719 (+292)
- `SELECT COUNT(*) ... MAX(report_date) ... MAX(release_ts)` → com_fin: 15729 rows, max_report_date=2026-09-22, max_release_ts=2026-09-28 19:30:00 | fut_fin: 15719 rows, max_report_date=2026-09-22, max_release_ts=2026-09-28 19:30:00
- Duplicate check `HAVING COUNT(*) > 1` → 0 rows (both tables)
- `release_ts <= report_date` violations → 0 (both tables)
- Future report dates `> 2026-10-03` → 0 (both tables)
- Cross-contamination (com_fin in fut / fut_fin in com) → 0 (both tables)
- Re-dry-run after write → 0 new candidates (idempotent)

## Design decisions

- Natural key: `(source_dataset, CFTC_Contract_Market_Code, report_date)` — uses the actual sanitized column from the live table, not display name.
- Release timestamp: Spark SQL `F.to_utc_timestamp` with `RELEASE_SAFETY_DAYS=3` (Monday 15:30 ET fallback), matching archive approach exactly.
- Append-only: left anti-join on natural key before append; `dropDuplicates` on incoming batch.
- `com_fin` and `fut_fin` failure isolation: a failure in one does not mark the other successful.
- Serverless Databricks Connect: `DatabricksSession.builder.serverless(True)`.