# VERDICT: rag-coverage-round10 — MiMo
**Status:** APPROVED
**Round:** 10

## Blocking findings addressed

1. **[P1] SparkLogWriter schema inference → CANNOT_DETERMINE_TYPE** [sec_rag_ingest.py:1737]
   → Added explicit `INGEST_LOG_SCHEMA` StructType (16 fields matching DATA_SCHEMAS.md).
   → `createDataFrame([row], schema=SparkLogWriter.INGEST_LOG_SCHEMA)` replaces bare `createDataFrame([row])`.

2. **[P1] Cold start: no DDL, reader crashes on missing table** [sec_rag_ingest.py:1323,1763]
   → Added `ensure_ingest_log_table()` with `CREATE TABLE IF NOT EXISTS` matching documented schema.
   → Called from `main()` before `run_ingest()`.
   → `SparkIngestLogReader.read_succeeded_accessions` and `read_max_attempt` now catch exceptions on table-not-found, return empty set / 0.
   → Fixed runbook: `bronze_sec_ingest_log` → `sec_ingest_log` at SEC_RAG_COVERAGE_RUNBOOK.md:174.

3. **[P1] Ownership conflict not recorded** [sec_rag_ingest.py:1283]
   → Anti-join now writes a `failed` / `error_code=ownership_conflict` sec_ingest_log entry BEFORE raising `AccessionOwnershipConflict`.

4. **[P1] Hard-coded schema in silver/05, silver/06**
   → Replaced all `bootcamp_students.evangoh_capstone` with `{catalog}.{schema}` in both SQL files (14 replacements).
   → Runner `run_silver_gold.py:run_step` already substitutes `{catalog}` and `{schema}`.

5. **[P2] MERGE metrics fallback to len(rows)** [sec_rag_ingest.py:1694, build_sec_embeddings.py:280]
   → Both sites now return `None` + log WARNING when DESCRIBE HISTORY fails.
   → `IngestLogEntry.rows_appended` changed to `Optional[int]`.
   → Accumulation skips `None` values (`if entry.rows_appended is not None`).
   → `_embed_batch` wrapper converts `None` → `0` for safe sum.

## Non-blocking notes

- Other SQL files (silver/01-04, gold/01-05) still hard-code `bootcamp_students.evangoh_capstone`. Out of scope for this round but should be addressed.
- `ensure_ingest_log_table` uses `CREATE TABLE IF NOT EXISTS` which is idempotent and safe for concurrent startup.

## Checks run

- `python3 -m pytest tests/rag tests/bronze -q` → **652 passed, 36 skipped** (new code)
- Old code verification (git archive copy at `/tmp/ragcov-old-round10`):
  - `TestSparkLogWriterSchema` → FAILED (TypeError: SparkLogWriter() takes no arguments)
  - `TestSparkIngestLogReaderColdStart` → FAILED (Exception not caught)
  - `TestOwnershipConflictAuditRow` → FAILED (0 audit rows, expected ≥1)
  - `TestSilverSqlPlaceholders` → FAILED (hard-coded schema still present)
  - `TestMergeMetricsNoCandidateFallback` → FAILED (returns 1 not None, falls back to len(rows))
  - All 9 new tests FAIL on old code. All 115 existing tests PASS on old code.

## Commits

- `6d16ced` fix(ingest): P1.1 explicit StructType + P1.2 ensure-table + P1.3 ownership audit + P2 bronze metrics
- `e036898` fix(embeddings): P2 return None on DESCRIBE HISTORY failure
- `66fbdd8` fix(silver): P1.4 {catalog}.{schema} placeholders in 05, 06
- `0129177` fix(docs): runbook table name correction
- `8c9597e` test(ingest): round 10 regression tests (9 new, all fail on old code)