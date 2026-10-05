# VERDICT: xbrl-B1b — MiMo
**Status:** APPROVED
**Round:** 2

## Blocking findings
- None

## Non-blocking notes
- Tests now extract and execute the REAL production SQL from `silver/09_silver_sec_xbrl_facts.sql` via `_extract_merge_using()` — the same approach used by `test_silver_sql_semantics.py`
- MERGE not supported by DuckDB, so the CTE chain is extracted from the USING clause and wrapped in INSERT INTO
- Four mutation functions apply string-level mutations to the production SQL text and execute in DuckDB to prove each defect
- `asof_facts()` contract updated: accepts `spark` session, reads production SQL from `silver/09_silver_sec_xbrl_facts_asof.sql`, returns `spark.sql(query, args={...})`

## Checks run
- `pytest -q tests/silver/test_sec_xbrl_facts.py` → 15 passed (1.15s)
- `pytest -q tests/silver tests/db` → 126 passed, 2 skipped (2.17s)
- `pytest -q tests/bronze tests/silver tests/db` → 479 passed, 19 skipped (4.90s)
- `pytest -q tests/silver/test_sec_xbrl_facts.py::TestNamedMutations -v` → 4 passed (0.67s)
- `pytest -q tests/db/test_xbrl_queries.py -v` → 9 passed (0.06s)

## Files modified

### `tests/silver/test_sec_xbrl_facts.py` — Major refactor
- Removed duplicated transform SQL (lines 138-276 in old version)
- `_extract_merge_using()` extracts CTE chain from MERGE USING clause in production SQL
- `_shim_for_duckdb()` handles `{catalog}.{schema}.` prefix, `current_timestamp()`, `:as_of` parameter
- `_run_silver_transform(conn, sql=None)` executes production SQL; accepts optional SQL override for mutations
- `_run_asof_query()` executes production as-of SQL from `silver/09_silver_sec_xbrl_facts_asof.sql`
- Four mutation functions apply string-level mutations to production SQL:
  - `_mutate_filed_date_instead_of_accepted_ts()` — replaces `f.accepted_ts` with `CAST(d.filed_date AS TIMESTAMP)`
  - `_mutate_drop_accession_from_key()` — removes `accession_number` from ROW_NUMBER PARTITION BY
  - `_mutate_asof_oldest_first()` — reverses sort to ASC
  - `_mutate_publish_unresolved()` — changes LEFT JOIN to INNER JOIN
- Column indices updated for production asof SQL (24 columns vs 10 in old hardcoded version)

### `db/xbrl_queries.py` — Contract fix
- `asof_facts(spark, as_of, ticker, concept, limit)` now accepts spark session as first arg
- Reads production SQL from `silver/09_silver_sec_xbrl_facts_asof.sql` via `_load_asof_sql()`
- Returns `spark.sql(sql, args={...})` with parameterized `:name` placeholders
- No f-string interpolation of user values

### `tests/db/test_xbrl_queries.py` — New file
- 9 unit tests using `FakeSpark` that records `sql()` calls
- Verifies: production SQL used, `:name` placeholders (no literal values), filters appended, limit clamped, returns DataFrame

## Named mutation evidence (all against PRODUCTION SQL)

| Mutation | Test | How it fails |
|----------|------|--------------|
| acceptance time → filed_date | `test_mutation_acceptance_time_replaced_with_filed_date` | Production SQL: accepted_ts=Mar 15; Mutated: filed_date=Mar 10 → different timestamp |
| drop accession from key | `test_mutation_drop_accession_from_key` | Production: 2 rows (different accessions); Mutated: 1 row (dedup collapse) |
| sort restatements oldest-first | `test_mutation_sort_restatements_oldest_first` | Production asof: 395B (amended); Mutated: 394B (original) |
| publish unresolved | `test_mutation_publish_unresolved_accessions` | Production: quality_status='unresolved_accession'; Mutated: 0 rows (INNER JOIN drops) |