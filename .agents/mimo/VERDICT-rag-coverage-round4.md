# VERDICT: rag-coverage-round4 — MiMo
**Status:** APPROVED
**Round:** 4

## Blocking findings
(none)

## Items addressed

1. **In-flight coalescing fixed** (`api/services/hybrid_retriever.py:319-372`).
   Load runs outside `_inflight_lock`; different tickers load in parallel; same-ticker
   callers coalesce on a shared `Future`. Re-check cache after acquiring lock. Pop marker
   in `finally`. Restored real concurrent tests: 2-thread coalescing, 4-thread coalescing,
   3-ticker parallelism. Failure isolation test now goes through `get_ticker_corpus`.

2. **Embedding parallelism** (`pipelines/build_sec_embeddings.py:61-175`).
   `ThreadPoolExecutor(max_workers=partitions)` over `toLocalIterator` batches. Each worker
   initialises its own model instance. Bounded in-flight futures. Tests verify concurrent
   workers (spy on threads) and output parity with sequential.

3. **Spark adapters wired into main()** (`pipelines/sec_rag_ingest.py:1153-1298`).
   `SparkUniverseReader` (reads `gold_tradable_universe`), `SparkAccessionReader`,
   `SparkDataWriter`, `SparkLogWriter` implemented and wired. No `--tickers` defaults to
   universe reader. CLI smoke test with dry-run passes.

4. **Placeholder User-Agents removed**.
   - `api/services/xbrl_client.py`: lazy `_get_user_agent()` fails closed on missing/example.
   - `config/settings.py`: reverted to `os.getenv("EDGAR_EMAIL", "")` (lazy, no placeholder).
   - `notebooks/02_ingest_sec_edgar.py`: fail-closed on missing EDGAR_EMAIL, deprecation notice.
   - Grep-style test `TestNoPlaceholderUserAgent` verifies no `example.com` in production files.

5. **Accession-ownership conflict** (`pipelines/sec_rag_ingest.py:1128-1130`).
   `except ValueError` re-raised before broad `except Exception`. Test
   `test_different_cik_accession_raises_value_error` verifies loud failure.

6. **DATA_SCHEMAS.md aligned** (`docs/DATA_SCHEMAS.md`).
   `gold_sec_coverage` updated to 7 cols matching SQL (ticker, cik, n_filings, n_chunks,
   first_filed, last_filed, last_ingest_ts). `sec_ingest_log` col count fixed to 16.

7. **pyspark-hidden failures fixed**.
   Removed module-level `sys.modules.setdefault` from `test_sec_embeddings_incremental.py`.
   All tests now use `fake_pyspark` fixture. `TestPerTickerDimModelValidation` also uses
   `fake_pyspark`. CI with pyspark hidden: 0 failures in tests/rag.

## Non-blocking notes

- `sec_cik_mapping_log` is documented in DATA_SCHEMAS.md but nothing writes to it. Not blocking.
- `build_sec_embeddings.build` returns `rows_already_embedded=-1` (anti-join makes count unknown).
- `config/settings.py` no longer raises at import time for missing EDGAR_EMAIL — consumers
  should validate at point of use (as `sec_rag_ingest.py` already does).

## Checks run

- `python3 -m pytest -q -p no:cacheprovider tests/rag` → 405 passed, 19 skipped (10s). PASS.
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase` → 678 passed, 6 failed (pre-existing COT), 67 skipped (166s). PASS (6 failures are pre-existing from base branch, also reported in round 1).
- `tests/rag` with pyspark hidden (`sitecustomize` in PYTHONPATH) → 405 passed, 19 skipped (8.5s). PASS.
- Full suite with pyspark hidden → 674 passed, 77 skipped, 0 failed (188s). PASS.
- `git diff --check` → clean.