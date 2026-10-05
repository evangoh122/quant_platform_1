Checker: Claude Sonnet subagent (DeepSeek out of credit)

===VERDICT START===
# VERDICT: rag-coverage check2 (re-check after round 3, HEAD b5450bf)
**Status:** CHANGES_REQUESTED

Summary of the 9 earlier findings: 1 RESOLVED (live raise), 2 RESOLVED for the request path, 3 RESOLVED (SQL), 4 RESOLVED (SQL, untested), 5 NOT RESOLVED (no real workers), 6 NOT RESOLVED (coalescing broken and its test weakened), 7 PARTIAL (code only, untested, swallowed in race path), 8 NOT RESOLVED, 9 PARTIAL (docs contradict the code). New: the production ingest CLI has no adapters.

## Blocking findings

1. **[api/services/hybrid_retriever.py:331-355] In-flight coalescing is broken, and different tickers serialize behind one lock.**
   `get_ticker_corpus` runs the load while holding `_inflight_lock` (an RLock). A second thread blocks on the lock instead of the Future. When it gets the lock, `_insert_ticker_corpus` has already popped the in-flight marker, and there is no cache re-check, so it loads again.
   Proof, run against a copy of HEAD with `_load_ticker_corpus` spied (0.3 s sleep):
   - 4 concurrent callers for NVDA gave `same-ticker loads: 4` (expected 1).
   - 3 distinct tickers took 0.90 s wall (parallel would be about 0.3 s). A slow Delta load for ticker A therefore blocks every cache miss for every other ticker.
   Fix: under the lock, only look up or create the Future. Run the load outside the lock. Re-check the cache after acquiring the lock. Pop the marker in a `finally`.
   Add a real two-thread test with an Event barrier and `join(timeout)`.

2. **[tests/rag/test_hybrid_retriever.py:2704-2739, 2742+] The 3C "test mocks" commit (4647b89) weakened tests.**
   - `TestInflightLoadCoalescing` previously started two threads and asserted `load_count == 1`. It was replaced by two sequential calls (cache hit), so it can no longer detect finding 1. The suite passes with the broken code.
   - `test_failure_isolation` used to assert that `get_ticker_corpus("AAA")` raises `CorpusUnavailableError`. It now calls `_load_ticker_corpus` directly and expects `RuntimeError`, so the get path and the error wrap are no longer covered.
   - The other changes in 4647b89 were stub additions (`_ColExpr.__and__/__or__/__invert__`, `toLocalIterator` mocks), which is benign.
   - 3A also removed `test_bm25_returns_empty_when_no_ticker_match` and the `dim .* != stored` assertions. Part of this is intended (ticker now required), but the dim/model guards are now tested only at load time.
   Fix: restore real concurrent coalescing and isolation tests, going through `get_ticker_corpus`.

3. **[pipelines/build_sec_embeddings.py:63-150] Finding 5 not fully resolved: no real embedding workers.**
   The `collect()` is replaced by `toLocalIterator()` with bounded batches, which is good. But `partitions` only calls `df.repartition(n)` (line 114-115), and the embed loop is a single sequential driver loop (`_embed_and_write_batch`). There is no ThreadPool or concurrent code (`grep ThreadPool|concurrent|Pool|max_workers` returns nothing). The spec called for 4 parallel embedding workers. The tests (`test_sec_embeddings_incremental.py`) only pass `partitions=4` into a mock.
   Fix: embed batches with a bounded `ThreadPoolExecutor(max_workers=partitions)` (bounded in-flight futures), or document and rename the parameter. Add a test that observes concurrency, with a timeout.

4. **[pipelines/sec_rag_ingest.py:1155-1190 (`main`), resources/jobs.yml:45-56] The production ingest job cannot run.**
   `main()` calls `run_ingest` with no `universe_reader`, `accession_reader`, `data_writer` or `log_writer`, and no concrete Spark/Delta implementations exist (`grep append_bronze_rows|read_existing_accessions|read_universe` shows only the Protocols and the test fakes).
   - The job with only `--catalog/--schema` raises `ValueError("Either tickers or universe_reader must be provided")`.
   - With `--tickers`, `data_writer is None` skips the write at line 1114, so nothing is appended and no log or CIK-mapping tables are written. The anti-join and ownership checks are no-ops because `accession_reader` is None.
   So nothing enters `bronze_sec_filings_v2`, and the whole feature is undelivered in production.
   Fix: implement the Databricks adapters (universe from `UNIVERSE_SQL`, existing accessions with cik/ticker, bronze append, log tables) and wire them in `main()`. Add a CLI smoke test with a fake Spark.

5. **[notebooks/02_ingest_sec_edgar.py:55, 114, 1025, 1517, 1687; api/services/xbrl_client.py:17] Finding 8 not resolved.**
   - The notebook still has its own `UNIVERSE_STK`, its own `build_cik_map`, `max_filings_per_ticker=8` and a placeholder User-Agent (`your_email@example.com`, line 1687). That is a second production ingestion definition.
   - `xbrl_client.py:17` still defaults the User-Agent to `research@example.com`.
   - Only `etl/extract_edgar.py` was fixed. The MiMo verdict acknowledges the notebook was left as is.
   Fix: make the notebook a thin caller of `pipelines.sec_rag_ingest`, or remove it from the production path and mark it deprecated. Drop the example.com defaults (fail closed like `sec_rag_ingest.py:931`).

6. **[pipelines/sec_rag_ingest.py:1062-1070, 1126; tests/rag/test_sec_rag_ingest.py:845-872] Accession-ownership conflict is untested, and the race-path conflict is swallowed.**
   - The plan-phase `ValueError` at line 1007 is real code, but `test_accession_ownership_conflict_fails` still passes SAME-owner accessions and asserts `skipped_existing_count == 2`. No test has a different CIK, and no `pytest.raises` covers the conflict. A regression would pass the suite.
   - The "race" conflict is raised inside the `try` whose broad `except Exception` (about line 1128) turns it into a `failed`/`exception` log row, so it does not fail loudly.
   Fix: add a test with a different-CIK existing accession that expects `ValueError`. Re-raise conflicts out of the per-filing try.

7. **[docs/DATA_SCHEMAS.md (added block), docs/SEC_RAG_COVERAGE_RUNBOOK.md] Docs contradict the code.**
   - DATA_SCHEMAS documents `gold_sec_coverage (5 cols)` as `ticker,cik,n_chunks,n_accessions,latest_accepted_ts`. The SQL (`gold/07_gold_sec_coverage.sql:48-55`) emits `ticker,cik,n_filings,n_chunks,first_filed,last_filed,last_ingest_ts`, and the runbook uses those names.
   - `sec_ingest_log` is labelled "17 cols" but lists 16.
   - `sec_cik_mapping_log` and the ingest-log tables are documented, but nothing creates or writes them (see finding 4).
   Fix: align the docs to the real DDL, and implement or remove the log tables.

8. **[tests/rag/test_sec_embeddings_incremental.py:13-18, test_hybrid_retriever.py (TestPerTickerDimModelValidation)] Tests fail with pyspark/databricks.connect hidden (a requirement).**
   With a `sitecustomize` setting `sys.modules[m]=None` for databricks.connect, pyspark, pyspark.sql, pyspark.sql.functions and pyspark.sql.types: `tests/rag` gives 7 failed, 390 passed (`ModuleNotFoundError: import of pyspark.sql halted` at `pipelines/build_sec_embeddings.py:85` x5 and `hybrid_retriever.py:198` x2). The full suite gives 7 failed (the same ones). This regressed from 5 to 7 failures since round 1 (the `sys.modules.setdefault` pattern is still used, and `TestPerTickerDimModelValidation` is not using `fake_pyspark`).
   Fix: use the `fake_pyspark` fixture (`monkeypatch.setitem`) in those tests.

## Non-blocking notes

- Finding 1 RESOLVED, proven live (not mocked). With only `_get_spark` faked at the table level, real `HybridRetriever().retrieve("x", ticker="ZZZZ")` raised `NoCoverageError` for both an empty coverage table and `n_chunks=0`. `retrieve("hello world")` raised `TickerRequiredError`. `search_sec_filings("ZZZZ")` returned `[{'error': 'no_coverage', 'ticker': 'ZZZZ'}]`. The in-repo `TestNoCoverage::test_retrieve_raises_when_no_coverage` itself monkeypatches `check_ticker_coverage` and so proves little, but the behaviour is correct.
- Finding 2: no all-corpus `collect()` is reachable from `retrieve`, `bm25_search`, `vector_search` or `get_ticker_corpus`. Every `collect()` is ticker-filtered at lines 211 and 222. `_load_corpus()` (417) and `reload_corpus()` (558-587) are dead code with no callers outside tests, and still do a full-corpus collect. Delete them.
- `check_ticker_coverage` costs a Spark round trip on every `retrieve`, even on a warm cache. Consider a short TTL cache.
- `search_sec_filings`: the `except (NoCoverageError, TickerRequiredError)` names are imported inside the `try`. An import failure would raise NameError. Move the imports above the `try`.
- Findings 3 and 4 are fixed in SQL. `silver/05` and `silver/06` derive the universe from `gold_tradable_universe` (CTE `sec_universe`, plus 16 hardcoded tickers), and `chunk_index` is `ROW_NUMBER() ... ORDER BY src.chunk_id` (bronze integer), matching the original semantics. The accession anti-join leaves existing rows untouched. However, no test executes or even greps the silver SQL (`grep` of tests for `05_silver_sec_sections` returns nothing), and no golden `chunk_index` parity test exists. Add a static test.
- `pipelines/run_silver_gold.py:84-97`: the `register_universe` docstring claims it combines `gold_tradable_universe`, but it still returns `load_universe()` (YAML). It is harmless now, since the SQL no longer uses the `universe` view, but it is misleading.
- `build_sec_embeddings.build` returns `rows_already_embedded=-1`, which is an observability regression.
- The silver `LEFT JOIN` anti-join reads the target table inside its own MERGE. Fine on Delta, but a partially written accession will never be completed. Mention it in the runbook.

## Checks run

- `python3 -m pytest -q -p no:cacheprovider tests/rag`: 397 passed, 19 skipped (7.4 s). PASS.
- Same with pyspark and databricks.connect hidden (`sitecustomize` in the scratch dir, `PYTHONPATH=<dir>:.`): 7 failed, 390 passed. FAIL (finding 8).
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase`: 670 passed, 6 failed, 67 skipped (101 s). The 6 failures are all `tests/bronze/test_refresh_bronze_cot.py` and pre-existing (also reported in round 1), unrelated to this slice.
- Full suite with the hide: 7 failed (the same 7 as the `tests/rag` hide run), 659 passed, 77 skipped.
- Coalescing and serialization proof (`/tmp/claude-1000/.../chk-ragcov/race.py`, run against the `git archive HEAD` copy): 4 loads for 4 callers, 0.90 s for 3 tickers. FAIL (finding 1).
- Live retrieve proof (`live.py`, same copy): NoCoverageError x2, TickerRequiredError, tool returned the no_coverage dict. PASS.
- `git diff --check ff546bc..HEAD`: clean. The worktree was clean (no tracked edits by me).
- `git show 4647b89 -- tests`: reviewed line by line, see finding 2.
- Not run: `ruff` (not installed).

===VERDICT END===
