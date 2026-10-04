# VERDICT: rag-databricks — MiMo
**Status:** APPROVED
**Round:** 1

## Blocking findings
- None.

## Non-blocking notes
- `gold_sec_chunk_embeddings` table must be created via `pipelines/build_sec_embeddings.py` on Databricks before the hybrid retriever can serve live queries. The batch script has not been executed in this session (no Databricks cluster available).
- The reranker model `cross-encoder/ms-marco-MiniLM-L-6-v2` will download on first use. If network access is restricted, the reranker degrades gracefully (returns docs unchanged).
- `sentence-transformers` + `rank-bm25` added to `requirements-app.txt` only (not `requirements.txt`), as instructed.
- BM25 index is rebuilt from the PIT-filtered subset on each query. For the 10,720-chunk corpus this takes <50 ms. If the corpus grows 10×, consider pre-filtering by ticker first.
- No Databricks Vector Search endpoint or index was created (per instructions). Documented as future option in comments.

## Checks run
- `python -m pytest tests/rag/test_hybrid_retriever.py -v` → 25/25 passed (1.65s)
  - TestRRFFuse: 7 tests (basic fusion, k validation, ticker boost, dedup, empty, single list)
  - TestBM25DenseFusion: 4 tests (BM25 relevance, vector search, hybrid fusion, ticker boost)
  - TestPITFilter: 5 tests (future excluded, exact boundary, None→now, missing ts, before scoring)
  - TestRerankerFallback: 3 tests (model unavailable, empty docs, top_k truncation)
  - TestTickerResolution: 5 tests (nvidia, micron, explicit override, no match, empty query)
  - TestEmbeddingBuildIdempotency: 1 test (second run writes 0 rows)

## Files created / modified
| File | Action |
|------|--------|
| `api/services/embeddings.py` | Created — provider abstraction (ST local / HF inference) |
| `api/services/hybrid_retriever.py` | Created — Delta corpus, BM25, cosine, RRF, PIT, ticker resolve |
| `api/services/reranker.py` | Created — cross-encoder reranker with graceful fallback |
| `pipelines/build_sec_embeddings.py` | Created — idempotent batch embed via MERGE |
| `agent/tools_retrieval.py` | Modified — `search_sec_filings` now uses hybrid retriever |
| `requirements-app.txt` | Modified — added `sentence-transformers`, `rank-bm25` |
| `tests/rag/test_hybrid_retriever.py` | Created — 25 offline tests |

## Commit
`51f6494` on `slice/rag-databricks` — not pushed to main.