# VERDICT: rag-coverage round9 — MiMo
**Status:** APPROVED
**Round:** 9

## Blocking findings
(none)

## Non-blocking notes
- N1: `SparkDataWriter._merge_lock` (class-level `threading.Lock`) serialises MERGE + ownership check + DESCRIBE HISTORY metrics read. View name uses `uuid.uuid4().hex[:12]`. View dropped in `finally` block. Test proves two concurrent threads get distinct view names and each reports its own inserted count.
- N2: `discover_filings` now returns `(filings, failed_history_urls)`. `run_ingest` records partial coverage in `sec_ingest_log` with `status="partial"`, `error_code="history_fetch_failed"`. `IngestResult` gains `partial_count` and `partial_tickers`. Summary log includes `partial=%d`.
- N3: `RateLimiter` gains `trigger_cooldown(seconds)` and `cooldown_remaining`. `acquire()` blocks during cooldown. `MAX_RETRY_AFTER = 120` — Retry-After above cap raises `SecClientError` (hard failure). 429/503 trigger global cooldown via `limiter.trigger_cooldown()`.
- N4: `_embed_and_write_batch` returns `inserted` directly (was `inserted if inserted > 0 else len(out_rows)`). Test proves 0 inserted → `rows_written == 0`.
- N5: `sys.path.insert(0, ...)` added to `build_sec_embeddings.py` and `sec_rag_ingest.py`. `jobs.yml` sec_embeddings env adds `loguru>=0.7.0` and `python-dotenv>=1.0.0`; sec_rag_ingest env adds `beautifulsoup4>=4.12.0` and `lxml>=4.9.0`. AST-based test verifies every top-level import is declared.
- BOM stripped from `sec_rag_ingest.py` (was causing `ast.parse` failures).
- `_make_mock_spark` now tracks batch sizes via `createDataFrame` interception and returns per-batch `numTargetRowsInserted` from DESCRIBE HISTORY.
- `test_hybrid_retriever.py::test_real_idempotency_count` mock updated to return proper metrics.

## Checks run
- `python3 -m pytest tests/rag tests/bronze -q` → 643 passed, 36 skipped, 0 failed