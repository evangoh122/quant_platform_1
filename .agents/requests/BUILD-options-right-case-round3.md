# BUILD fix/options-right-case round 3 (builder: MiMo; checker: DeepSeek; reviewer: Codex)

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch fix/options-right-case. Descriptive commits. LF endings.
NEVER delete or weaken existing tests. Codex review: .agents/codex/VERDICT-options-right-case-review.md (2 blocking, 1 minor).

1 (blocking). The production day writer `_shape_day()` (notebooks/refresh_bronze_options.py:464, :481-482) builds `right` itself; tests only
   cover `parse_opra_symbol()`, which has no production caller. Refactor so `_shape_day()` uses ONE canonicalisation function (e.g.
   `canonical_day_right(raw) -> 'PUT'|'CALL'`) that is directly tested, and add a test that runs `_shape_day()` itself (fake_pyspark or
   a minimal local DataFrame — follow the existing test patterns in tests/bronze/test_refresh_bronze_options.py) and asserts the emitted
   `right` values are 'PUT'/'CALL'. Mutation proof (in /tmp copy, paste output): change `_shape_day()` output back to lowercase → a test FAILS.
2 (blocking). Canonical encodings, documented and handled (Claude's decision):
   - gold/02_gold_options_features.sql: accept all known encodings — normalise with
     `CASE WHEN UPPER(`right`) IN ('PUT','P') THEN 'PUT' WHEN UPPER(`right`) IN ('CALL','C') THEN 'CALL' END` (one CTE column, then compare
     to 'PUT'/'CALL') for the day CTE AND the p25/c25 quote CTEs. notebooks/01_ingest_market_data.py (Quick Start) writes 'C'/'P' — leave
     that writer unchanged but make gold robust to it.
   - docs/DATA_SCHEMAS.md: for bronze_options_day and bronze_options_quotes, state the allowed values per writer (refresh day path: 'PUT'/'CALL';
     refresh quotes path: 'put'/'call'; Quick Start: 'P'/'C') and that consumers MUST normalise via the shared CASE expression.
   - Extend the DuckDB semantic test fixtures with 'P'/'C' rows → counted. Extend the repo-wide scan to flag a bare `UPPER(right) = 'PUT'`
     without the alias handling? No — just ensure gold uses the normalised column; the scan stays as is.
3 (minor). sql/maintenance/2026-10-04_normalize_options_right_case.sql:37 has CRLF — convert the file to LF. Add a test asserting no CRLF in
   sql/maintenance/*.sql.
Acceptance: python -m pytest -q tests/gold tests/bronze tests/silver (pre-existing pytz failures excepted); pyspark hidden
(PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps) same.
.agents/mimo/VERDICT-options-right-case-round3.md with counts + mutation output. Commit everything.
