# VERDICT: xbrl-B1b-r8 — MiMo
**Status:** APPROVED
**Round:** 8

## Blocking findings
None.

## Non-blocking notes
- The `bronze_with_ts` CTE's MIN/MAX window functions still partition by the full12-column key including accession_number. This is correct — first/last observed timestamps should track per-original-key, not per-normalized-key.
-70,212 of152,703 facts are `unresolved_accession` (filings older than bronze_sec_filings_v2's2024-09+ window) — that is by design, as noted in the BUILD request.

## Checks run
- `python3 -m pytest tests/silver/test_sec_xbrl_facts.py -v` →37 passed (2.41s)
- `python3 -m pytest tests/silver/test_xbrl_facts_ddl.py -v` →13 passed (0.30s)

## Changes made

### silver/09_silver_sec_xbrl_facts.sql
- **Root cause fix:** Moved ROW_NUMBER() dedup from `deduped_bronze` (raw values) to `deduped_normalized` (after TRIM/UPPER normalization). Two bronze rows that differ only by whitespace/case in key columns now correctly collapse to one silver row.
- **Conflict detection:** Added `conflicting_values` quality_status via `MAX(value_decimal) OVER (...) IS DISTINCT FROM MIN(value_decimal) OVER (...)` in the `deduped_normalized` CTE. Never silently averages or drops conflicting values.
- **CTE restructuring:** `bronze_with_ts` (timestamps) → `normalized` (TRIM/UPPER) → `deduped_normalized` (ROW_NUMBER + conflict + LEFT JOIN filings_accepted + quality_status). Final SELECT is `SELECT * FROM deduped_normalized WHERE rn = 1`.
- **Additional normalization:** Added TRIM to `period_end`, `instant`, `frame` (previously untrimmed).

### tests/silver/test_sec_xbrl_facts.py
- Added `TestRound8DedupWithConflict` (3 tests): identical facts →1 row, conflicting values → flagged, agreeing values → ok.
- Added `TestRound8SourceKeyUniqueness`: asserts `count(*) == count(DISTINCT key)` over production SELECT.
- Added `TestRound8MergeIdempotentDedup`: MERGE twice with duplicates → no extra rows.
- Added `TestRound8MutationRemoveDedup` (2 tests): removing `WHERE rn = 1` causes duplicates and breaks key uniqueness.
- Updated mutation helpers (`_mutate_filed_date_instead_of_accepted_ts`, `_mutate_drop_accession_from_key`, `_mutate_remove_dedup_filter`) to match new SQL structure.

### tests/silver/test_xbrl_facts_ddl.py
- Fixed `_parse_normalized_cte_columns` to use paren-depth-aware character-by-character parsing (FROM inside OVER() clauses was breaking the line-by-line approach).
- Now extracts from `deduped_normalized` CTE and filters internal columns (`rn`, `ingested_at`, etc.).