===VERDICT START===
# VERDICT: rag-coverage round 12 — DeepSeek (checker)
**Status:** APPROVED
**Round:** 12

## Summary

The Codex P1 from `.agents/codex/VERDICT-rag-coverage-r4.md` ("unknown ingest metrics still become a job-level
zero") is fixed at commit `4415955`. `IngestResult.total_rows_appended` is now `Optional[int]`, and in BOTH the
threaded and serial aggregation paths any successful filing whose `rows_appended is None` sets the total to
`None` (idempotent, guarded by an `elif ... is not None` accumulation). The summary log renders `rows=unknown`
via a `%s` + ternary, never `0`. The runbook idempotency gate now states `unknown` does NOT satisfy the gate.
Nine new behavioural tests (driving the real `run_ingest` entry point with a fake writer) assert
`[None,None]→None`, `[3,None]→None`, `[0,0]→0`, `[2,5]→7` in both modes. Restoring the skip-None aggregation
(mutation) and running the new tests against the parent commit `01f9f34` both yield 5 failures (red phase).

## Verification

### 1. `total_rows_appended` is Optional; None propagates in both paths

- `pipelines/sec_rag_ingest.py:1099` `total_rows_appended: Optional[int] = 0` (was `int`).
- `pipelines/sec_rag_ingest.py:168` `DataWriter.append_bronze_rows(...) -> Optional[int]` (was `int`).
- Threaded path `pipelines/sec_rag_ingest.py:1496-1499`:
  `if entry.rows_appended is None: result.total_rows_appended = None`
  `elif result.total_rows_appended is not None: result.total_rows_appended += entry.rows_appended`
- Serial path `pipelines/sec_rag_ingest.py:1518-1521`: identical None-propagation.
- Once set to `None`, the `elif ... is not None` guard prevents any later `int +=` (idempotent, thread-safe).
- Confirmed via the new tests which call the real `run_ingest` entry point with `SeqWriter` fake writers
  (not a helper): `[None,None]→None`, `[3,None]→None`, `[0,0]→0`, `[2,5]→7`, each in serial and threaded modes.

### 2. Consumers are None-safe; None never coerced to 0

- Summary log `pipelines/sec_rag_ingest.py:1533-1542`: `rows=%s` (was `%d`) with
  `"unknown" if result.total_rows_appended is None else result.total_rows_appended`. No `%d`/`format` on the
  value remains (`grep 'rows=%d' pipelines/` → only a stale `.pyc`).
- `main()` exit code uses `result.failed_count`, not `total_rows_appended` (`sec_rag_ingest.py:2031`).
- No `dbutils.jobs.taskValues` anywhere in `pipelines/ notebooks/ jobs/ scripts/`.
- No `notebooks/`, `jobs/`, or `scripts/` file references `total_rows_appended`/`rows_appended` (grep clean).
- Per-filing `IngestLogEntry.rows_appended: Optional[int] = None` (`sec_rag_ingest.py:242`); Spark log schema
  nullable (`StructField("rows_appended", IntegerType(), True)` at `:1781`); DDL `rows_appended INT` (no
  `NOT NULL`) at `:1837`; `SparkDataWriter` returns `inserted: Optional[int]` at `:1714`.
- All pre-existing `assert result.total_rows_appended == 0` / `> 0` tests still pass (no test weakened).

### 3. Runbook gate text

- `docs/SEC_RAG_COVERAGE_RUNBOOK.md:161-165`: states `rows=unknown` is **NOT** idempotency satisfaction; it means
  MERGE could not determine inserted count (DESCRIBE HISTORY no metrics); instructs to re-run and investigate
  `sec_ingest_log WHERE rows_appended IS NULL`.

### 4. Mutation + red phase

- Mutation (`/tmp/ragcov-mutation`, restore skip-None + `int = 0`): **5 failed, 4 passed**
  (all `*_none_*`, `*_mixed_*`, and `test_mutation_skip_none_aggregation_fails` fail; zeros/real-values pass).
- Red phase (`/tmp/ragcov-parent`, parent commit `01f9f34` + new test file): **5 failed, 4 passed** (same set).

## Checks run

- `python3 -m pytest tests/rag tests/bronze -q` → **673 passed, 36 skipped, 0 failed** (19.4s)
- `python3 -m pytest tests/rag/test_sec_rag_ingest.py::TestTotalRowsAppendedAggregation -q` (HEAD) → **9 passed**
- Mutation (`/tmp/ragcov-mutation`) named tests → **5 failed, 4 passed**
- Red phase (`/tmp/ragcov-parent` @ `01f9f34`) named tests → **5 failed, 4 passed**
- `grep 'rows=%d' pipelines/` → no source match
- `grep -rn 'taskValues' pipelines/ notebooks/ jobs/ scripts/` → no match

## Non-blocking notes

- `SparkIngestLogReader.read_succeeded_accessions` still interpolates `run_id` into a `WHERE` clause
  (`sec_rag_ingest.py`). Pre-existing, runbook-controlled, not user-facing input; out of scope for this round.
- The summary `rows=unknown` is a job-level aggregate only; the authoritative per-filing `None` remains queryable
  in `sec_ingest_log.rows_appended`. This matches the embeddings-aggregate pattern and is the intended behaviour.
===VERDICT END===
