# BUILD: RAG coverage round 3 (MiMo), THREE STAGES, commit after each

> **IMPLEMENT NOW.** No confirmation questions. Commit after EACH stage (3A, 3B, 3C) so a timeout
> keeps the finished stages. NEVER delete or weaken existing tests.

DeepSeek (`.agents/deepseek/VERDICT-rag-coverage.md`, read ALL 9 findings) says the core feature isn't
delivered. Work through them in this order.

## Stage 3A: the live retrieval path (findings 1, 2, 6). Commit "rag-coverage 3A".
- `HybridRetriever.retrieve()` / `search_sec_filings()`:
  - resolve the ticker (explicit, else `resolve_ticker_from_query`);
  - if there's none, raise `TickerRequiredError` → `{"error":"ticker_required"}`;
  - call `check_ticker_coverage()`: 0 chunks → `NoCoverageError` → `{"error":"no_coverage","ticker":…}`.
  - Never return a silent `[]`.
- REMOVE every all-corpus fallback: in `get_ticker_corpus`, and `_load_corpus()` from the BM25 and
  vector paths when the ticker is empty. There is no full-corpus `collect()` anywhere in the request
  path.
- Real tests through `retrieve()` (no mocking of HybridRetriever):
  - `ticker_required`, `no_coverage`;
  - the LRU bound and eviction with `RAG_TICKER_CACHE_MAX=2` across 3 tickers;
  - in-flight load coalescing (two threads, one load; spy count == 1, with timeouts);
  - per-ticker failure isolation;
  - per-ticker dim/model validation;
  - PIT before scoring per ticker.

## Stage 3B: data flow (findings 3, 4, 5). Commit "rag-coverage 3B".
- **Silver gating.** `silver/05` and `silver/06` must take their ticker set from `gold_tradable_universe`
  (all symbols ever in it, i.e. a CTE over DISTINCT symbol) unioned with the existing 16 SEC tickers.
  NOT `config/universe.yaml`. Update `pipelines/run_silver_gold.py` to match. Test: the SQL references
  `gold_tradable_universe`, and a new ticker present in bronze_v2 reaches silver (SQL-structure test,
  plus a fake-Spark test if feasible).
- **`chunk_index`.** Restore the ORIGINAL ordering rule (the bronze integer `chunk_id` order). Prove
  parity: existing rows keep identical `chunk_index`/`chunk_id`.
- **Embeddings.**
  - No driver `collect()` of all unembedded rows. Process in bounded batches (e.g. `toLocalIterator()`,
    or by partition with `mapInPandas`/`foreachPartition`) with a max batch size.
  - Make `partitions`/workers real (`repartition(n)`, plus per-partition model init).
  - Test that memory stays bounded: a fake source of 10k rows never materialises more than the batch
    size at once (spy).

## Stage 3C: ingestion hygiene and docs (findings 7, 8, 9). Commit "rag-coverage 3C".
- The accession-ownership conflict check: the existing-accession reader returns accession →
  (cik, ticker). An accession already owned by a different CIK fails loudly. Test the conflict path.
- One production definition. `notebooks/02_ingest_sec_edgar.py` and `etl/extract_edgar.py` must use
  `pipelines/sec_rag_ingest.py` (CIK map, parsing, User-Agent from config). Remove the hard-coded
  `UNIVERSE_STK`, `max_filings_per_ticker=8` and the `research@example.com` fallback. A missing
  User-Agent config → a clear error.
- Docs: `docs/DATA_SCHEMAS.md` (ingest log, mapping log, coverage table) and
  `docs/BRONZE_REFRESH_PLAN.md`.

Acceptance after each stage:
- `python3 -m pytest -q -p no:cacheprovider tests/rag` in under 3 min;
- the full suite with `--ignore=tests/lakebase`, 0 failures;
- the same suite with pyspark and databricks.connect hidden.

LF line endings only. Don't touch `.agents/dispatch.sh`. Leave no scratch files. Write
`.agents/mimo/VERDICT-rag-coverage-round3.md` with one section per stage.
