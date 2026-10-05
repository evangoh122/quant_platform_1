# VERDICT: xbrl-B1b-r7 — MiMo
**Status:** APPROVED
**Round:** 7

## Blocking findings
None.

## Non-blocking notes
- The DDL step in `run_silver_gold.py` reuses the step name `silver_sec_xbrl_facts` (same as the MERGE step) so `count(spark, name)` returns 0 after DDL and N after MERGE. This is correct — the DDL creates the table (0 rows), then the MERGE populates it.
- The DDL uses `USING DELTA` which is Databricks-specific. DuckDB tests strip it via regex in the shim. This is the same pattern as other Spark-only syntax in the codebase.
- The `split_statements` function in `run_silver_gold.py` strips comment lines before splitting on `;`, so the DDL's comment header is safely ignored at runtime.

## Checks run
- `pytest tests/silver/test_xbrl_facts_ddl.py -v` → 13/13 passed
- `pytest tests/silver/test_sec_xbrl_facts.py -v` → 30/30 passed (existing tests unbroken)
- Commit `92b85e9` on `feat/xbrl-silver` — 3 files changed, 544 insertions

## Files created/modified
1. **`silver/09a_silver_sec_xbrl_facts_ddl.sql`** (new) — `CREATE TABLE IF NOT EXISTS` with all 26 columns the MERGE writes, explicit types, `NOT NULL` only where source can never produce NULL, `USING DELTA`.
2. **`pipelines/run_silver_gold.py`** (modified) — DDL step registered before the MERGE step in STEPS list.
3. **`tests/silver/test_xbrl_facts_ddl.py`** (new) — 13 tests covering DDL+MERGE idempotency, column match (parsed from production files), NOT NULL constraint match, and 4 mutation proofs (remove DDL step, drop column, drop NOT NULL column, merge-fails-without-DDL).