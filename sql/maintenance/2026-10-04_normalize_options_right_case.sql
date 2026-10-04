-- 2026-10-04_normalize_options_right_case.sql
--
-- DELIBERATE ONE-OFF EXCEPTION to docs/BRONZE_REFRESH_PLAN.md:13 ("no Bronze
-- UPDATE").  Owner-approved: the newer refresh_bronze_options.py (2026-09-08
-- .. 2026-10-01) wrote lowercase 'put'/'call' for ~6M rows (18 trading days),
-- while the existing 146M rows use uppercase 'PUT'/'CALL'.  Gold SQL uses
-- UPPER(right) so the mismatch is cosmetic, but canonicalising to uppercase
-- keeps the column consistent and prevents future drift.
--
-- One-off: this script is run once, manually, on a SQL warehouse.  It will
-- NOT be re-run or automated.  Future ingestion writes lowercase for quotes
-- and uppercase for day-agg; the quotes path will be backfilled separately
-- if/when bronze_options_quotes is refreshed.
--
-- IDEMPOTENT: Running twice is safe — UPPER('PUT') = 'PUT', UPPER('CALL') =
-- 'CALL', so the WHERE clause excludes already-normalised rows.
--
-- Run on Databricks SQL warehouse. Do NOT run in CI.

-- ── Pre-check: counts by `right` value ──────────────────────────────────
SELECT `right`, COUNT(*) AS n
FROM bootcamp_students.evangoh_capstone.bronze_options_day
WHERE `right` IN ('put', 'call', 'PUT', 'CALL')
GROUP BY `right`
ORDER BY `right`;

-- ── Backfill ──────────────────────────────────────────────────────────────
UPDATE bootcamp_students.evangoh_capstone.bronze_options_day
SET `right` = UPPER(`right`)
WHERE `right` IN ('put', 'call');

-- ── Post-check: counts by `right` value ─────────────────────────────────
SELECT `right`, COUNT(*) AS n
FROM bootcamp_students.evangoh_capstone.bronze_options_day
WHERE `right` IN ('put', 'call', 'PUT', 'CALL')
GROUP BY `right`
ORDER BY `right`;