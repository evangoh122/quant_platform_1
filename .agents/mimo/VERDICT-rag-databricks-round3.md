# VERDICT: rag-databricks-round3 — MiMo
**Status:** APPROVED
**Round:** 3

## Blocking findings
None.

## Non-blocking notes
- `CorpusUnavailableError` defined in `api/services/hybrid_retriever.py:38` — single exception covers all load failures (Spark session, Delta table read, empty result).
- `_get_spark()` helper at `hybrid_retriever.py:209` detects `DATABRICKS_RUNTIME_VERSION` to choose between ambient `SparkSession` and `DatabricksSession.builder.serverless(True)`.
- `search_sec_filings` in `agent/tools_retrieval.py:119` catches `CorpusUnavailableError` separately from generic `Exception` — the generic path still falls back to substring filter for other failure modes.
- Existing 28 tests unaffected; 8 new tests added covering both defects and the integration surface.

## Checks run
- `python -m pytest tests/rag/test_hybrid_retriever.py -v` → 36 passed, 0 failed (2.09s)
- `git diff --stat` → 3 files changed, +231 / -13