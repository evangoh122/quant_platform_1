# BUILD-REQUEST: rag-databricks — ROUND 3 (fail loudly; work under databricks-connect)

**Builder:** MiMo · **Checkers:** Claude, then DeepSeek

## Verified LIVE by the coordinator — keep all of it
- `gold_sec_chunk_embeddings`: 10,720 rows, 384-d, 1 model, metadata complete. Run 1 wrote 10,720;
  an independent run 2 wrote **0** in 6.6s (real idempotency).
- `search_sec_filings("NVDA", "export restrictions China")`: 10 vector + 10 BM25 → RRF → rerank top 5,
  relevant NVDA 10-Q passages with accession numbers; `as_of=2025-01-01` returns only the 2024-11-21
  filing and **0** post-as_of results. Rag_workbench's logic works on Databricks.

## Defects
1. **Silent failure.** `api/services/hybrid_retriever.py:_load_corpus` catches the load error, logs it,
   and retrieval returns `[]`. "Corpus failed to load" is then indistinguishable from "no matching
   filings" — unacceptable for an agent that must not fabricate or silently omit evidence. Raise a
   specific exception (e.g. `CorpusUnavailableError`), and have `search_sec_filings` surface a
   structured "retrieval unavailable" result the agent can report, never an empty list.
2. **Session acquisition.** The loader uses `SparkSession.builder.getOrCreate()`, which databricks-connect
   rejects outside a Databricks runtime ("Only remote Spark sessions using Databricks Connect are
   supported"). Use `DatabricksSession.builder.serverless(True).getOrCreate()` when not inside a
   Databricks runtime (detect `DATABRICKS_RUNTIME_VERSION`), and the ambient session inside one.

## Tests
- Corpus load failure → `CorpusUnavailableError` / structured unavailable result, **not** `[]`.
- Session selection picks DatabricksSession outside a runtime (mock both).
- All 28 existing tests still pass.

Do not rebuild embeddings. Edit only `api/services/hybrid_retriever.py`, `agent/tools_retrieval.py`
(the `search_sec_filings` wrapper), `tests/rag/test_hybrid_retriever.py`. LF line endings.
**Commit your work.** Write `.agents/mimo/VERDICT-rag-databricks-round3.md`.
