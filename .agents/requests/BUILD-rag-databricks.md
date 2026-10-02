# BUILD-REQUEST: rag-databricks

**Branch:** `slice/rag-databricks` (worktree `/home/jianj/code/qp1-rag`; based on the integration
branch, so `api/`, `agent/` and the silver/gold layer are all present)
**Builder:** MiMo · **Checkers:** Claude, then DeepSeek
**Owner's instruction:** "For RAG in the databricks use the same logic as RAG_Workbench."

## Port Rag_workbench's retrieval logic unchanged; swap only the storage layer

Source of truth (read-only — do not edit that repo): `/home/jianj/code/Rag_workbench/api/services/`
`hybrid_retriever.py`, `embeddings.py`, `reranker.py`, `rag_engine.py`, `structure_chunker.py`.

| Stage | Rag_workbench (keep exactly) |
| :-- | :-- |
| Dense | `BAAI/bge-small-en-v1.5`, 384-d, sentence-transformers; provider abstraction from `embeddings.py` (`EMBEDDING_PROVIDER` / `ST_EMBEDDING_MODEL`) |
| Sparse | BM25 via `rank_bm25.BM25Okapi`, same tokenization, same ticker boost |
| Candidates | each side fetches `top_k * 2` |
| Fusion | Reciprocal Rank Fusion, `rrf_k = 60` (`rrf_fuse`) |
| Rerank | cross-encoder `cross-encoder/ms-marco-MiniLM-L-6-v2`, `top_k = 5`, graceful fallback if the model is unavailable |
| Chunking | `structure_chunker` (already in this repo at `api/services/structure_chunker.py`; 200–1,500 chars) |

Rag_workbench stored vectors in DuckDB and scanned them brute-force. **On Databricks:**
- Corpus: `bootcamp_students.evangoh_capstone.silver_sec_sections` — measured 10,720 chunks,
  128 filings, 16 tickers, chunks ≤ 1,500 chars, `accepted_ts` 2024-09-11 → 2026-08-26.
- **New table `gold_sec_chunk_embeddings`**: `chunk_id`, `accession_number`, `ticker`,
  `accepted_ts`, `embedding ARRAY<FLOAT>` (384), `embedding_model`, `embedded_ts`. Built by a
  batch script/job (`pipelines/build_sec_embeddings.py`) via databricks-connect serverless,
  **idempotent** (only embed chunk_ids not already present for that `embedding_model`).
- Query time: load chunk text + embeddings once (≈16 MB at 384-d float32), cache in process,
  brute-force cosine like Rag_workbench. BM25 index built from the same chunks.
- **Do not** create a Databricks Vector Search endpoint or index (billable, and its built-in hybrid
  fusion is not Rag_workbench's logic). Mention it as a future option in docs only.

## Point-in-time (required by the rubric)
Every retrieval takes an `as_of` timestamp (default now) and may only return chunks with
`accepted_ts <= as_of`. Apply the filter **before** BM25/dense scoring, not after reranking, so
future filings can never influence ranking. Test: a chunk accepted after `as_of` never appears,
even when it is the best lexical/semantic match.

## Wire it in
- `api/services/hybrid_retriever.py`, `api/services/embeddings.py`, `api/services/reranker.py`
  (ported), with the Delta-backed corpus loader.
- `agent/tools_retrieval.py::search_sec_filings(symbol, query, as_of=None, top_k=5)` uses the
  hybrid retriever (today it is a substring filter over 50 rows). Return chunk text, accession,
  form, `accepted_ts`, source URL, and the fused/rerank scores so answers stay auditable.
- Keep `structure_chunker` as the chunker of record.

## Tests (offline; mark live ones `@pytest.mark.databricks`)
- RRF: same fixtures and expected order as Rag_workbench's `rrf_fuse`.
- BM25 + dense fusion on a tiny in-memory corpus with a stub embedder (no model download).
- PIT filter test above.
- Reranker fallback when the model cannot load.
- Embedding build idempotency: a second run embeds 0 new chunks.

## Run (live)
Run `pipelines/build_sec_embeddings.py` once and paste: rows written (expect 10,720), embedding
dimension 384, and a second run writing 0. Then one live `search_sec_filings("NVDA", "export
restrictions China", as_of=...)` call, pasting the top results with accession numbers.

## Dependencies
`sentence-transformers` and `rank_bm25` are needed. Add them to `requirements-app.txt` only (do not
edit `requirements.txt`). If model download is impossible in your environment, say so — do not
substitute a different model silently.

## Constraints
Do not edit `ml/`, `silver/`, `gold/0*`, `db/`, `frontend/`, `.github/`, `conftest.py`, `pytest.ini`,
`.agents/dispatch.sh`, or anything in `/home/jianj/code/Rag_workbench`. LF line endings.
**Commit your work.** Write `.agents/mimo/VERDICT-rag-databricks.md`.
