# VERDICT: rag-coverage-round11 — MiMo
**Status:** APPROVED
**Round:** 11

## Summary
Fixed the single P1 from Codex round 3: missing MERGE metrics were silently reported as 0 instead of None + WARNING.

## Changes made

### `pipelines/sec_rag_ingest.py` (commit 66a730b)
- `SparkDataWriter.append_bronze_rows`: `inserted = 0` → `inserted = None`
- Added WARNING log when `DESCRIBE HISTORY` returns no rows
- Added WARNING log when `operationMetrics` lacks `numTargetRowsInserted`
- Exception handler unchanged (already returned None + WARNING)

### `pipelines/build_sec_embeddings.py` (commit e0ca919)
- `_embed_and_write_batch`: `inserted = 0` → `inserted = None`; added WARNING for empty history and missing key
- `_embed_batch`: removed `or 0` coercion — now propagates None
- `build()`: added `rows_unknown` flag; if any batch returns None, `rows_written` is None (not partial sum, not 0)

### `tests/rag/test_merge_metrics.py` (commit 0798921)
- 12 new behavioural tests covering both writers and aggregate
- Red phase captured: 5 failures on HEAD before fix, 0 after

## Blocking findings
- None

## Non-blocking notes
- The 3 pre-existing collection errors (`test_chat_engine.py`, `test_graph_rag_engine.py`, `test_langgraph_engine.py`) are due to missing `api.db` and `api.services.rag_engine` modules — unrelated to this change.

## Checks run
- `python -m pytest tests/rag/test_merge_metrics.py -v` → 12 passed
- `python -m pytest tests/rag/test_merge_metrics.py tests/rag/test_sec_rag_ingest.py tests/rag/test_sec_embeddings_incremental.py -q` → 157 passed
- `git diff --stat` → 3 files changed (pipelines/sec_rag_ingest.py, pipelines/build_sec_embeddings.py, tests/rag/test_merge_metrics.py)