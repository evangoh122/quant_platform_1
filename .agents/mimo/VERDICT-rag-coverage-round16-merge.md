# VERDICT: rag-coverage-round16-merge — MiMo
**Status:** APPROVED
**Round:** 16b

## Summary
Merge of origin/main into slice/rag-coverage completed. All merge-related conflicts resolved.

## Per-file resolution

### agent/tools_retrieval.py — CONFLICT (search_sec_filings)
- **Branch side contributed:** `except (NoCoverageError, TickerRequiredError)` — structured error responses for no_coverage and ticker_required. NoCoverage does NOT fall through to substring fallback.
- **Main side contributed:** `except Exception` substring fallback — queries `silver_sec_sections` with PIT `accepted_ts <= as_of` filter, `retrieval_mode="substring_fallback"`, `chunk_id`, `_warning`.
- **Resolution:** Kept both. Exception handler order: `(NoCoverageError, TickerRequiredError)` → `EmbeddingConfigError` → `CorpusUnavailableError` → `Exception` (substring fallback). NoCoverageError/TickerRequiredError are caught BEFORE the generic Exception, so they never reach the fallback.

### api/services/hybrid_retriever.py — CONFLICT (bm25_search, vector_search, retrieve)
- **Branch side contributed:** Per-ticker LRU cache (`get_ticker_corpus`), `TickerRequiredError` for empty ticker, `NoCoverageError` for missing tickers.
- **Main side contributed:** Global corpus path (`_load_corpus()` / `_bm25_docs` / `_embeddings_map`), no ticker required.
- **Resolution:** Both paths preserved. When `ticker` is non-empty, uses per-ticker LRU cache. When `ticker=""` and corpus is pre-loaded (via `install_offline_corpus`), uses global corpus. When `ticker=""` and corpus is NOT pre-loaded, raises `TickerRequiredError`.

### evals/rag_eval/corpus.py — CONFLICT (install_offline_corpus)
- **Branch side contributed:** Per-ticker LRU cache architecture.
- **Main side contributed:** Global corpus population via `install_offline_corpus`.
- **Resolution:** Extended `install_offline_corpus` to also build per-ticker `TickerCorpus` objects and insert into `_ticker_cache`, so both retrieval paths work. Saves/restores the ticker cache in the context manager.

### tests/rag/test_sec_retrieval_tool.py — CONFLICT (substring fallback tests)
- **Branch side contributed:** Tests expecting NO substring fallback for generic exceptions.
- **Main side contributed:** Tests expecting substring fallback.
- **Resolution:** Updated branch tests to expect substring fallback (main's behavior). Added `fake_pyspark` fixture for proper pyspark function mocking.

### tests/rag/test_hybrid_retriever.py — CONFLICT (test_spark_table_error)
- **Branch side contributed:** Test expecting `retrieval_unavailable` with no substring fallback.
- **Main side contributed:** Substring fallback behavior.
- **Resolution:** Updated test to expect substring fallback with proper mock setup.

## Checks run
- `python3 -m pytest tests/rag tests/bronze -q --ignore=tests/rag/test_langgraph_engine.py` → 1105 passed, 5 failed
- All 5 failures are from `test_merge_metrics.py::TestSparkDataWriterMetrics` — pre-existing Windows-only pyspark issue (pyspark.sql.types.IntegerType not available without pyspark installed). On WSL with pyspark, these pass. NOT merge-related.
- `test_zz_isolation.py::test_databricks_connect_not_polluted` → PASSED
- `test_zz_isolation.py::test_pyspark_not_polluted` → PASSED
- All 18 rag_eval tests from origin/main → PASSED (the substring fallback and offline corpus issues are fixed)

## Non-blocking notes
- `test_langgraph_engine.py` has a pre-existing collection error (references `api.services.rag_engine` which doesn't exist). Ignored via `--ignore`.
- `test_merge_metrics.py` failures are Windows-only (pyspark not installed). Environment-only, not code defects.
- LF endings maintained. `.agents/dispatch.sh` not touched.