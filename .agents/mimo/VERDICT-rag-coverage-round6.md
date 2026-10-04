# VERDICT: rag-coverage-round6 — MiMo
**Status:** APPROVED
**Round:** 6

## Blocking findings
- None

## Non-blocking notes
- Item 4 (COT test isolation): Root cause is 3 pre-existing collection errors in `tests/rag/test_chat_engine.py`, `test_graph_rag_engine.py`, `test_langgraph_engine.py` — they import `api.db.database` which does not exist in the repo. When pytest encounters these collection errors, it aborts before running any tests (including the COT Idempotency tests). When the 3 files are excluded, all 581 tests pass (33 skipped). This is not caused by this branch's files. Fix: add `api.db` module or mark those tests with `@pytest.mark.skip` until the module exists.

## Checks run
- `pytest tests/rag tests/bronze --ignore=test_chat_engine,test_graph_rag_engine,test_langgraph_engine -q` → 581 passed, 33 skipped
- `pytest tests/rag --ignore=test_chat_engine,test_graph_rag_engine,test_langgraph_engine -q` → 421 passed, 16 skipped
- `pytest tests/rag/test_sec_rag_ingest.py -q` → 87 passed
- `pytest tests/rag/test_sec_rag_ingest.py::TestNotebookThinWrapper -q` → 8 passed
- `pytest tests/rag/test_sec_rag_ingest.py::TestCikMappingLog tests/rag/test_sec_rag_ingest.py::TestSparkCikMappingLogWriterSchema -q` → 6 passed
- `pytest tests/rag/test_sec_rag_ingest.py::TestMainEndToEnd::test_main_write_mode_writes_filings_and_log -q` → 1 passed

## Mutation proofs (item 2)

### Schema match test
```
tests/rag/test_sec_rag_ingest.py::TestSparkCikMappingLogWriterSchema::test_schema_matches_documented_schema
```
Asserts StructType fields match docs/DATA_SCHEMAS.md exactly:
- Field names: `[ticker, lookup_symbol, cik, status, reason, mapped_ts, run_id]`
- Nullability: `[False, True, True, False, True, True, True]`
- Types: `[StringType, StringType, StringType, StringType, StringType, TimestampType, StringType]`
**Mutation: remove schema= kwarg → test FAILS** (no schema passed to createDataFrame)

### cik=None handling
```
tests/rag/test_sec_rag_ingest.py::TestSparkCikMappingLogWriterSchema::test_cik_none_row_written_with_schema
```
A row with `cik=None` is written without error when explicit schema is provided.
**Mutation: remove schema → Spark type inference raises on cik=None**

### Batch write (N tickers → 1 write call)
```
tests/rag/test_sec_rag_ingest.py::TestSparkCikMappingLogWriterSchema::test_batch_single_write_call
```
5 entries → 1 `createDataFrame` call (not 5).
**Mutation: per-ticker writes in append_mapping_log → createDataFrame called 5 times → test FAILS**

### Buffer cleared after flush
```
tests/rag/test_sec_rag_ingest.py::TestSparkCikMappingLogWriterSchema::test_buffer_cleared_after_flush
```
Second `flush()` is a no-op (0 additional writes).
**Mutation: remove self._buffer.clear() → second flush writes again → test FAILS**

### Flush called exactly once in run_ingest
```
tests/rag/test_sec_rag_ingest.py::TestCikMappingLog::test_flush_called_exactly_once
```
`run_ingest()` calls `flush()` exactly once after the CIK mapping loop.
**Mutation: remove flush() call → flush_count=0 → test FAILS**

## Item 1: Legacy notebook thin wrapper
- `notebooks/02_ingest_sec_edgar.py`: 3,684 lines → 75 lines
- Delegates to `pipelines.sec_rag_ingest.main(argv)`
- No User-Agent, requests.get, BeautifulSoup in notebook
- `main()` now accepts optional `argv` parameter
- Updated `docs/MERGE_PLAN.md:38` and `README.md:74,82`
- 8 new tests verify thin wrapper correctness

## Item 3: Strengthened main() write-mode test
- Asserts exact ticker, cik, accession_number, form_type, accepted_ts per row
- Asserts chunk_ids and filing_sections per filing (4 sections × 1 chunk each)
- Asserts log entries: accession, form_type, cik, status
- Asserts CIK mapping log: ticker, cik, status, flush_count