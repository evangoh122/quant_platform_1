# BUILD: RAG coverage round 4 (MiMo)

> **IMPLEMENT NOW.** No confirmation questions. Commit after EACH numbered item. You must RESTORE
> the two tests weakened in commit 4647b89 (see item 1). NEVER weaken a test to make it pass: fix the
> code instead.

Checker (`.agents/deepseek/VERDICT-rag-coverage-check2.md`, read it fully). Findings 1–4 from
earlier are now resolved. Remaining blocking items:

1. **In-flight coalescing is broken, and its tests were weakened.**
   - The load runs while holding `_inflight_lock`, so 4 concurrent callers for one ticker do 4
     loads, and different tickers load serially.
   - Fix: take the lock only to look up or create a per-ticker `Future`/`Event`, release it, do the
     load outside the lock, then publish.
   - RESTORE the real two-thread coalescing test, and the per-ticker isolation test that 4647b89
     replaced with sequential or direct calls. Also add:
     - 4 threads on one ticker → exactly 1 load;
     - 3 tickers in parallel → finishes in about the time of one load (spy durations; generous
       margins; thread timeouts).
2. **Embeddings have no real workers.** `partitions` only repartitions, and embedding runs
   sequentially. Implement real parallelism:
   - `mapInPandas` / `foreachPartition`, initialising the model per partition, on Databricks; OR
   - a bounded `ThreadPoolExecutor` of N workers over the `toLocalIterator` batches locally.

   Keep memory bounded. Test that N workers process the batches concurrently (spy) and that
   results equal the sequential output.
3. **The production ingest `main()` passes no Spark adapters.** With no `--tickers` it raises
   `ValueError`; with `--tickers` nothing is written.
   - Wire the real Spark readers and writers into `main()`.
   - With no `--tickers`, the default ticker set is `gold_tradable_universe` (DISTINCT, current or
     ever, via a flag).
   - Test `main()` end-to-end with fake Spark adapters: the dry-run writes 0 rows and the write mode
     appends.
4. **Placeholder User-Agents remain.**
   - The notebook has its own universe and `your_email@example.com`.
   - `xbrl_client.py` defaults to `research@example.com`.

   Remove every placeholder; the User-Agent comes from config or a secret. Missing → a clear error.
   The notebook must delegate to `pipelines/sec_rag_ingest.py`. Add a grep-style test that no
   `example.com` User-Agent remains in production code.
5. **The accession-ownership conflict is untested, and the race-path conflict is swallowed.**
   - Add a test where the same accession belongs to a different CIK → it fails loudly.
   - Remove the broad `except` that swallows it.
6. **Docs:** `DATA_SCHEMAS.md`'s `gold_sec_coverage` columns must match the SQL exactly, and the log
   tables must be written by code or removed from the docs.
7. **pyspark-hidden failures:** 7 failures in `test_sec_embeddings_incremental.py` and
   `TestPerTickerDimModelValidation` when pyspark is hidden. Make them pass with pyspark hidden (use
   fakes), as CI has no pyspark.

Also check `tests/bronze/test_refresh_bronze_cot.py` (6 failures in the full suite on this branch).
Are they pre-existing from the base branch? If so, note them in the verdict and don't fix them here.

Run:
- `python3 -m pytest -q -p no:cacheprovider tests/rag` in under 3 minutes;
- the full suite with `--ignore=tests/lakebase`;
- both again with pyspark and databricks.connect hidden.

LF line endings only. Don't touch `.agents/dispatch.sh`. Write `.agents/mimo/VERDICT-rag-coverage-round4.md`.
