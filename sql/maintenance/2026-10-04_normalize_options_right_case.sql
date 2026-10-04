-- 2026-10-04_normalize_options_right_case.sql
--
-- One-off backfill: normalize bronze_options_day.right to uppercase.
--
-- WHY: The newer refresh_bronze_options.py (2026-09-08 .. 2026-10-01) wrote
-- lowercase 'put'/'call' for 5,986,723 rows (18 trading days), while the
-- existing 146M rows use uppercase 'PUT'/'CALL'. Gold SQL now compares on
-- UPPER(right) so the mismatch is cosmetic, but canonicalising to uppercase
-- keeps the column consistent with docs/BRONZE_REFRESH_PLAN.md and prevents
-- future drift.
--
-- IDEMPOTENT: Running twice is safe — UPPER('PUT') = 'PUT', UPPER('CALL') =
-- 'CALL', so the WHERE clause excludes already-normalised rows.
--
-- Run on Databricks SQL warehouse. Do NOT run in CI.

-- ── Pre-check: counts by right value ──────────────────────────────────────
SELECT right, COUNT(*) AS n
FROM bootcamp_students.evangoh_capstone.bronze_options_day
WHERE right IN ('put', 'call', 'PUT', 'CALL')
GROUP BY right
ORDER BY right;

-- ── Backfill ──────────────────────────────────────────────────────────────
UPDATE bootcamp_students.evangoh_capstone.bronze_options_day
SET right = UPPER(right)
WHERE right IN ('put', 'call');

-- ── Post-check: counts by right value ─────────────────────────────────────
SELECT right, COUNT(*) AS n
FROM bootcamp_students.evangoh_capstone.bronze_options_day
WHERE right IN ('put', 'call', 'PUT', 'CALL')
GROUP BY right
ORDER BY right;