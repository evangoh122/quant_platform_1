# VERDICT: post-merge-round5 — MiMo
**Status:** APPROVED
**Round:** 5

## Blocking findings
- None.

## Non-blocking notes
- `EmbeddingConfigError` defined in `api/services/exceptions.py` (shared module) to avoid circular imports between `embeddings.py` and `hybrid_retriever.py`.
- `get_embeddings()` now raises `EmbeddingConfigError` (subclass of `CorpusUnavailableError`) for: missing HF_TOKEN, unknown provider, unloadable model. Previously returned `None`.
- `vector_search()` no longer checks for `None` from `get_embeddings()` — the exception propagates through `retrieve()` → `search_sec_filings()` → `retrieval_unavailable`.
- Transient `embed_query()` failures still degrade to `bm25_only` + `_warning="dense_unavailable"` via the existing `except Exception` in `retrieve()`.
- `TestEmbedderFailureDegradesToBM25Only` fixture now populates `_embeddings_map` with real vectors (non-empty) so `vector_search` does NOT short-circuit. Each test asserts the embedder WAS called (call counter > 0).
- 5 new E2E tests added in `TestEmbeddingE2EThroughSearchSecFilings`: missing token, dim mismatch, model mismatch, transient raise with NVDA hit, transient raise respecting as_of.

## Checks run
- `python3 -m pytest -q -p no:cacheprovider tests/rag tests/test_schema_env_override.py` → 302 passed, 19 skipped (with pyspark stubs via fake_pyspark fixture)
- Verified `EmbeddingConfigError` is subclass of `CorpusUnavailableError`: `True`
- Verified `get_embeddings()` raises for `EMBEDDING_PROVIDER=bogus`: `EmbeddingConfigError`
- Verified `get_embeddings()` raises for `huggingface` without token: `EmbeddingConfigError`
- LF line endings confirmed (no CRLF in modified files)
- No secrets committed. No `.agents/dispatch.sh` touched.