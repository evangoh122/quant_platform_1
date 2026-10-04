# CHECK: rag-databricks (DeepSeek, independent checker)

Branch `slice/rag-databricks`, HEAD after MiMo round 5. Read-only: do not modify
production code or tests. Do scratch work under /tmp. Write
`.agents/deepseek/VERDICT-rag-databricks-check.md` between ===VERDICT START=== and
===VERDICT END=== with Status APPROVED or CHANGES_REQUESTED.

Scope: `api/services/{hybrid_retriever,embeddings,reranker}.py`,
`pipelines/build_sec_embeddings.py`, `agent/tools_retrieval.py::search_sec_filings`,
tests in `tests/rag/`.

Spec: same logic as Rag_workbench.
- bge-small-en-v1.5, 384-d
- BM25Okapi
- top_k×2 candidates from each retriever
- RRF with k=60
- cross-encoder ms-marco-MiniLM-L-6-v2 rerank to top 5
- point-in-time `as_of` filter applied BEFORE scoring

Check, hardest first:
1. **Point-in-time in every path.** Hybrid, BM25, dense, AND the substring fallback.
   - Fallback: `as_of.strftime(...)` drops the tzinfo and casts it in the Spark session
     timezone. Is that correct when `as_of` is tz-aware but not UTC, or when the session
     timezone isn't UTC? What type is `accepted_ts`?
   - Hybrid path: what happens with a naive `as_of`? Does comparing it with an aware
     `accepted_dt` raise, and then silently drop into the fallback?
   - Show concrete failing inputs if any.
2. **Fidelity to Rag_workbench.** Check the model names, candidate counts, the RRF
   formula/k, and reranker top-n.
3. **No silent degradation.** Fallback results are tagged. `CorpusUnavailableError`
   returns a structured error, never `[]`. No raw exception text reaches the result.
4. **Tests.** They call the production code. Would they catch a broken RRF or a removed
   PIT filter? Prove it by mutating a /tmp copy.
5. **Embeddings pipeline.** Idempotent. No look-ahead in which chunks get embedded.

Run `python3 -m pytest tests/rag -q`.

## Re-check (rounds 6-7)
Re-verify your three earlier blocking findings against HEAD (rounds 6-7). Also check
the round-7 client-timezone fix:
- `_load_corpus` and `build_sec_embeddings` now read `unix_timestamp(accepted_ts)`.
- Claude's live smoke: `as_of=2025-01-01 +08:00` and naive `2025-01-01` both return
  `retrieval_mode=hybrid` with only the 2024-11-20T21:31Z NVDA filing.

Write `.agents/deepseek/VERDICT-rag-databricks-check2.md`.
