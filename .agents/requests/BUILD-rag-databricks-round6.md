# BUILD: rag-databricks round 6 (MiMo)

DeepSeek returned CHANGES_REQUESTED (`.agents/deepseek/VERDICT-rag-databricks-check.md`).
Read it first. Fix all three blocking findings.

1. **One `as_of` normaliser.** Add `_normalize_as_of(as_of)` in
   `api/services/hybrid_retriever.py`:
   - `None` → `datetime.now(timezone.utc)`
   - naive → treat as UTC (document this)
   - aware → `.astimezone(timezone.utc)`
   - Call it at the top of `HybridRetriever.retrieve`, `bm25_search`,
     `vector_search`, `_pit_filter` and `search_sec_filings`.
   - A naive `as_of` must no longer raise or fall into the fallback.

2. **Timezone-safe fallback.** In `agent/tools_retrieval.py`, compare `accepted_ts` against
   a value that doesn't depend on the Spark session timezone. For example, pass the
   normalised UTC datetime as `F.lit(<aware UTC datetime>)`, or compare
   `F.to_utc_timestamp(...)` / epoch seconds `F.unix_timestamp`. Pick one and justify it
   in the verdict. Test it: `as_of = 2025-06-01 00:00 +08:00` must exclude a filing
   accepted at `2025-05-31 20:00Z`.

3. **Point-in-time tests through the real retrieval path.** Add tests that call
   `bm25_search`, `vector_search` (mock the embedding/Spark parts as needed) and
   `retrieve` with a future-dated chunk, and assert it's excluded. Prove the tests work:
   in a /tmp copy, remove the PIT filter from bm25_search and from vector_search
   separately. Each mutation must fail at least one test. Paste the outputs in the
   verdict.

Also: a naive `as_of` through `search_sec_filings` returns `retrieval_mode == "hybrid"`
(add a test).

Rules: LF line endings only. Don't touch `.agents/dispatch.sh`. `python3 -m pytest tests/rag -q`
must pass. Commit. Write `.agents/mimo/VERDICT-rag-databricks-round6.md`.
