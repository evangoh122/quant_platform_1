# BUILD: RAG coverage round 2 (MiMo)

> **IMPLEMENT NOW.** Do not stop to ask for confirmation. Commit early and often, at least after each
> numbered part, so a timeout never loses work.

Round 1 (saved on branch `wip/rag-coverage-r1`, commit "WIP: MiMo RAG coverage round 1") timed out
uncommitted, and Claude found two blocking problems:
1. **Existing tests deleted.** `tests/rag/test_hybrid_retriever.py` lost about 2,000 lines, including
   the PIT, embedding-config and mutation tests from PR #19. NEVER delete or weaken existing tests.
   If an API you change breaks them, update the call sites minimally and keep every assertion. The
   count of test functions in `tests/rag` must be ≥ the base branch's count. Report both counts.
2. **The test suite hangs.** `pytest tests/rag` ran for over 10 minutes. Find the hanging test(s),
   most likely the rate limiter (a real `sleep`), the coalesced-load `Future`, or the RLock
   concurrency tests. Use the injectable clock/sleep everywhere. Every concurrency test has a
   timeout (`future.result(timeout=5)`, joined threads with a timeout). Add `pytest-timeout`-style
   guards, or `signal.alarm` per test, so a hang fails fast.

## How to proceed
- Start from the CURRENT branch `slice/rag-coverage`, which is clean. Cherry-pick or copy what's
  useful from `wip/rag-coverage-r1`: `pipelines/sec_rag_ingest.py`, `pipelines/_http_adapter.py`,
  `gold/07_gold_sec_coverage.sql`, the new test files and the runbook.
- Re-apply the retriever and pipeline changes carefully, against the spec
  `.agents/requests/BUILD-rag-coverage.md`, preserving all existing behaviour and tests.
- Check `silver/05` and `silver/06`: the round-1 diff rewrote large parts. Changes must be minimal
  and keep chunk_id parity (an existing filing re-chunked gives identical chunk_ids). Prove it with
  the parity test.
- Commit in stages:
  - (a) ingestion + CIK mapping + tests;
  - (b) per-ticker LRU retriever + tests;
  - (c) embeddings incremental + job;
  - (d) coverage table + `no_coverage`/`ticker_required` errors;
  - (e) the runbook.

## Acceptance
- `python3 -m pytest -q -p no:cacheprovider tests/rag` finishes in under 3 minutes with 0 failures.
- The same suite with pyspark/databricks.connect hidden.
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase` gives 0 failures.
- The test-function count in `tests/rag` is ≥ the base. Show
  `git diff --stat origin/slice/rag-coverage -- tests/` with no large deletions.

LF line endings only. Don't touch `.agents/dispatch.sh`. Leave no scratch files. Write
`.agents/mimo/VERDICT-rag-coverage.md`.
