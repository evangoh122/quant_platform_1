# VERDICT: rag-coverage-round3 — MiMo
**Status:** APPROVED
**Round:** 3

## Stage 3A: Live retrieval path (findings 1, 2, 6)

### Changes made
- `HybridRetriever.retrieve()` now raises `TickerRequiredError` when no ticker can be resolved from query or argument
- `retrieve()` calls `check_ticker_coverage()` which raises `NoCoverageError` for tickers with zero chunks
- `bm25_search()` and `vector_search()` now require a ticker parameter (raise `TickerRequiredError` if empty)
- Removed all-corpus fallback from `get_ticker_corpus()`, `bm25_search()`, and `vector_search()`
- Fixed deadlock: `_inflight_lock` changed from `threading.Lock` to `threading.RLock`
- Updated all existing tests to use per-ticker LRU cache instead of global corpus path
- Added new tests: `TestTickerRequired` (5 tests), `TestNoCoverage` (2 tests), `TestLRUBoundAndEviction` (2 tests), `TestPITBeforeScoringPerTicker` (1 test), `TestPerTickerFailureIsolation` (1 test), `TestPerTickerDimModelValidation` (2 tests), `TestInflightLoadCoalescing` (1 test)

### Blocking findings addressed
- Finding 1: `TickerRequiredError` and `NoCoverageError` now wired into `retrieve()` and `search_sec_filings()` — verified by `TestTickerRequired` and `TestNoCoverage`
- Finding 2: All-corpus fallback removed from `get_ticker_corpus`, `bm25_search`, `vector_search` — verified by `TestBM25TickerFilter`
- Finding 6: LRU bound/eviction tests, per-ticker isolation, dim/model validation, coalescing, PIT per ticker — all implemented and passing

## Stage 3B: Data flow (findings 3, 4, 5)

### Changes made
- `silver/05_silver_sec_sections.sql`: Universe filter changed from `SELECT symbol FROM universe` to CTE over `gold_tradable_universe` + 16 hardcoded SEC tickers
- `silver/06_silver_sec_entities.sql`: Same universe CTE change
- `chunk_index` ordering restored: `ORDER BY src.chunk_id` (bronze integer) instead of `ORDER BY src.record_key` (sha256 hash)
- `pipelines/build_sec_embeddings.py`: Replaced `anti_join_df.collect()` with `anti_join_df.toLocalIterator()` for bounded memory; added `repartition(n)` for parallel partitions; refactored batch writes into `_embed_and_write_batch()` helper

### Blocking findings addressed
- Finding 3: Silver transforms now filter by `gold_tradable_universe` CTE, not `config/universe.yaml`
- Finding 4: `chunk_index` ordering uses bronze `chunk_id` (integer ordinal), not `record_key` (hash)
- Finding 5: Embeddings pipeline uses `toLocalIterator()` instead of `collect()`, bounded batch writes, `repartition(n)`

## Stage 3C: Ingestion hygiene and docs (findings 7, 8, 9)

### Changes made
- `ExistingAccessionReader` protocol changed from `Set[str]` to `Dict[str, Tuple[str, str]]` (accession → (cik, ticker))
- Accession-ownership conflict: if an accession exists with a different CIK, `run_ingest` raises `ValueError`
- `etl/extract_edgar.py`: Removed `research@example.com` fallback; missing `EDGAR_EMAIL` raises `ValueError`
- `docs/DATA_SCHEMAS.md`: Added `sec_ingest_log`, `sec_cik_mapping_log`, `gold_sec_coverage` schemas
- `docs/BRONZE_REFRESH_PLAN.md`: Added SEC ingestion reference

### Blocking findings addressed
- Finding 7: Accession-ownership conflict detection implemented and tested
- Finding 8: `etl/extract_edgar.py` no longer falls back to `research@example.com`; raises on missing config
- Finding 9: Data schemas and bronze refresh plan docs updated

## Checks run
- `python3 -m pytest -q -p no:cacheprovider tests/rag` → **397 passed, 19 skipped, 6.24s** — PASS
- `python3 -m compileall api/services pipelines agent` → clean — PASS
- `git diff --check HEAD~4..HEAD` → clean — PASS

## Non-blocking notes
- The notebook `notebooks/02_ingest_sec_edgar.py` still has hard-coded `UNIVERSE_STK` and `max_filings_per_ticker=8`. These are non-production demo code; the production path is `pipelines/sec_rag_ingest.py`. Full notebook refactor was not completed in this round.
- Some complex mock-based tests (e.g., `TestStoredIndexDimensionGuard::test_mixed_stored_dimensions_unavailable`) required `_ColExpr.__and__` support in the pyspark stub.

## Conclusion
All 9 DeepSeek findings addressed. The retrieval path now enforces ticker requirements, silver transforms use the full tradable universe, embeddings stream in bounded batches, and accession ownership conflicts are detected. 397 tests pass.