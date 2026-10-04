# BUILD fix/options-right-case (builder: MiMo; checker: Claude Sonnet subagent; reviewer: dataexpert Claude)

IMPLEMENT NOW. Do not ask "Shall I proceed?". Branch fix/options-right-case (already checked out). Commit after each item with
descriptive messages. NEVER delete or weaken existing tests. LF line endings.

## Live finding (Claude, 2026-10-04, SQL warehouse)
bronze_options_day.`right` is MIXED CASE:
- 2024-01 .. 2026-09-04: 'PUT' / 'CALL' (uppercase) — 146M rows
- 2026-09-08 .. 2026-10-01: 'put' / 'call' (lowercase) — 5,986,723 rows (18 trading days), written by the newer
  notebooks/refresh_bronze_options.py (line ~206: `right = "call" if right_raw == "C" else "put"`).
gold/02_gold_options_features.sql compares `right = 'PUT'` / `right = 'CALL'` (put_volume/call_volume → put_call_ratio),
so every lowercase day gets put_volume = call_volume = 0 → put_call_ratio wrong/NULL. gold_options_features currently ends at
2026-09-04. The quotes-snapshot CTEs (p25/c25) compare lowercase 'put'/'call' against bronze_options_quotes.

## 1. Gold SQL: case-insensitive
In gold/02_gold_options_features.sql, compare on `UPPER(right)` everywhere (`UPPER(right) = 'PUT'` etc.), including the
quotes CTEs (p25/c25). grep the whole repo (silver/, gold/, pipelines/, ml/, strategies/, api/, analytics_nl/) for any other
comparison on `right` / option side and fix it the same way. List every site in your verdict.

## 2. Canonical case going forward (ingestion)
Decide ONE canonical form for bronze_options_day.right: uppercase 'PUT'/'CALL' (matches 146M existing rows and
docs/DATA_SCHEMAS.md if it says so — check). Make refresh_bronze_options.py write uppercase for day aggs. Do NOT change
bronze_options_quotes semantics unless its docs say uppercase — check and state.

## 3. One-off backfill SQL (do NOT run it; Claude runs it live)
Add sql/maintenance/2026-10-04_normalize_options_right_case.sql:
`UPDATE bootcamp_students.evangoh_capstone.bronze_options_day SET right = UPPER(right) WHERE right IN ('put','call');`
plus a verification SELECT (counts by right) before/after, with a header comment explaining why and that it is idempotent.

## 4. Tests
- A test that parses gold/02 and fails if any comparison on `right` is not case-insensitive (regex over the SQL: any
  `right\s*(=|IN)\s*'` not wrapped in UPPER/LOWER fails).
- A DuckDB semantic test: run the `day` CTE logic from the real gold/02 SQL (extract from the file, minimal documented
  translation shim only if a Databricks-only function blocks DuckDB — e.g. replace convert_timezone/make_interval
  expression with a literal) on fixture rows mixing 'PUT','put','CALL','call' → put_volume/call_volume count ALL of them.
  Mutation proof (in /tmp copy, paste output): revert one UPPER → test FAILS.
- Ingestion test: the day-agg row builder emits 'PUT'/'CALL'.
- Repo-wide test: no other SQL/py site compares option side case-sensitively (same regex as above over silver/ gold/ pipelines/).

## Acceptance
python -m pytest -q tests/gold tests/bronze tests/silver (whatever exists) all pass; pyspark hidden
(PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps) same.
Write .agents/mimo/VERDICT-options-right-case.md with counts, the site list and mutation output. Commit everything.
