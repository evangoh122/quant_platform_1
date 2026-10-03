# CHECK: RAG coverage beyond 16 tickers (DeepSeek)

Branch `slice/rag-coverage`. Spec: `.agents/requests/BUILD-rag-coverage.md` plus the round-2 request.
MiMo committed 4 stages:
- (a) ingestion + CIK mapping;
- (b) per-ticker LRU retriever + `NoCoverageError`/`TickerRequiredError`;
- (c–e) incremental embeddings, anti-join, coverage table.

The test count went 370 → 455. `tests/rag` runs in about 7 s, so the hang is fixed. Read-only;
scratch work in /tmp. Write `.agents/deepseek/VERDICT-rag-coverage.md` (===VERDICT START/END===,
Status).

Check, with proofs:
1. **Test integrity.** Round 1 deleted about 2,000 lines of tests. Diff `tests/` against the merge
   base and confirm no assertion was weakened or removed without a reason. One behaviour change is
   deliberate and must be confirmed SAFE:
   `test_missing_accepted_ts_included_defensively` → `test_missing_accepted_ts_excluded`. Chunks with
   a missing `accepted_ts` are now EXCLUDED from PIT results (fail-closed). Is this consistent
   everywhere: BM25, dense, the fallback, and the KG?
2. **Ingestion.**
   - SEC fair access: ≤10 req/s, User-Agent from config, backoff on 429/503.
   - `accepted_ts` comes from the EDGAR acceptance datetime, in UTC.
   - Idempotent (second run appends 0), resumable, dry-run.
   - Missing CIKs are logged, never silently dropped.
   - Class shares handled.
3. **Chunk parity.** An existing filing re-chunked gives identical `chunk_id`s, and the rewrites of
   `silver/05` and `silver/06` are minimal.
4. **Per-ticker LRU.**
   - bounded by `RAG_TICKER_CACHE_MAX`;
   - in-flight loads coalesce;
   - eviction is safe while a request uses the entry;
   - per-ticker failures are isolated;
   - PIT runs before scoring per ticker;
   - the stored dim/model check is per ticker;
   - there is NO all-corpus fallback.
5. **Error contract.** `ticker_required` and `no_coverage` are distinct from `retrieval_unavailable`,
   and none of them leak secrets.
6. **Concurrency tests** have timeouts and use the injectable clock/sleep; nothing sleeps for real.

Run `python3 -m pytest -q -p no:cacheprovider tests/rag`, and the full suite with
`--ignore=tests/lakebase`, both with pyspark and databricks.connect hidden too.
