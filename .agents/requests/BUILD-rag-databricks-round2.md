# BUILD-REQUEST: rag-databricks — ROUND 2

**Builder:** MiMo · **Checkers:** Claude, then DeepSeek

## Verified by the coordinator
- Retrieval code is correct: with `rank_bm25` installed, `tests/rag/test_hybrid_retriever.py` → **25 passed**.
  RRF k=60, `bge-small-en-v1.5` (384-d), `ms-marco-MiniLM-L-6-v2`, PIT filter before scoring. Keep it.
- The coordinator ran `pipelines/build_sec_embeddings.py` from WSL: it embedded **10,720/10,720**
  chunks, then **failed to write** — `gold_sec_chunk_embeddings` does not exist.

## Defects
1. `pipelines/build_sec_embeddings.py:105` MERGEs into a table that is never created. Add
   `CREATE TABLE IF NOT EXISTS` with the schema from the round-1 spec: `chunk_id`, `accession_number`,
   `ticker`, `accepted_ts`, `embedding ARRAY<FLOAT>`, `embedding_model`, `embedded_ts`. The script
   currently writes only chunk_id/embedding/model/ts — add the missing columns.
2. **`"second_run_rows": 0` at `:117` is hard-coded.** A reported measurement must be measured.
   Compute idempotency for real: count chunk_ids already embedded for this model before embedding, and
   report how many were actually written.
3. Embed only chunks not yet present for this `embedding_model` (the round-1 requirement) — check that
   a second run computes **zero** embeddings, not that it merges the same ones again.

Do not run the live build — the coordinator runs it from WSL (your Windows shell has no Databricks
config). Add/adjust tests (stubbed embedder) for: table creation, idempotent skip, real counts.
Edit only `pipelines/build_sec_embeddings.py`, `api/services/*` you created, `tests/rag/test_hybrid_retriever.py`.
LF line endings. **Commit your work.** Write `.agents/mimo/VERDICT-rag-databricks-round2.md`.
