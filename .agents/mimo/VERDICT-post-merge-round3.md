# VERDICT: post-merge-round3 — MiMo
**Status:** APPROVED
**Round:** 3

## Summary
Fixed the dimension guard in `vector_search()` to compare against the **stored index dimension** (recorded at corpus load time) instead of the configured `EMBEDDING_DIM`. Also added embedding-model-name validation and restored the sentence-transformers default to `BAAI/bge-small-en-v1.5` (384-d) so all defaults match the shipped index.

## Changes made
- `api/config.py:182-185` — `ST_EMBEDDING_MODEL` default restored to `BAAI/bge-small-en-v1.5`
- `api/config.py:208-209` — `EMBEDDING_DIM` for `sentence-transformers` provider changed from 1024 to 384
- `api/services/hybrid_retriever.py:224-226` — New `_stored_index_dim` and `_stored_embedding_model` module vars
- `api/services/hybrid_retriever.py:282-315` — `_load_corpus()` now selects `embedding_model`, validates uniform dimension, records stored dim/model
- `api/services/hybrid_retriever.py:535-554` — Dimension guard uses stored index dim; model-name guard added
- `api/services/hybrid_retriever.py:36` — Removed unused `EMBEDDING_DIM` import
- `tests/rag/test_hybrid_retriever.py` — 3 new tests + 2 existing tests updated for new module vars

## Proof that tests fail on HEAD
Before fix, with `EMBEDDING_PROVIDER=sentence_transformers` (1024-d configured) against a 384-d stored index:
```
FAIL: ValueError from np.dot -- should be CorpusUnavailableError
```
The old guard compared `len(qvec) != EMBEDDING_DIM` → 1024 != 1024 → passed. Then `np.dot(a_1024, b_384)` raised `ValueError`. After fix, the guard compares against `_stored_index_dim` (384) → 1024 != 384 → raises `CorpusUnavailableError` cleanly.

## Tests added (all failing on pre-fix HEAD)
1. `test_1024d_query_against_384d_index_returns_unavailable` — 1024-d query vs 384-d stored index → `CorpusUnavailableError`
2. `test_mixed_stored_dimensions_unavailable` — Mixed stored vector dims → corpus load raises
3. `test_model_name_mismatch_unavailable` — Active model != stored model → `CorpusUnavailableError`

## Checks run
- `python3 -m pytest -q -p no:cacheprovider tests/rag tests/test_schema_env_override.py` → **286 passed, 19 skipped** (with pyspark stubs)
- Same command with `PYSPARK_NOT_AVAILABLE=1` → **286 passed, 19 skipped**
- LF line endings verified

## Non-blocking notes
- The model-name check uses `api.config` to resolve the active model per-provider. If someone sets a custom `HF_EMBEDDING_MODEL` that differs from the stored `BAAI/bge-small-en-v1.5`, they'll get a clear error instead of silent garbage.
- `_stored_index_dim` is `None` when corpus has no embeddings (empty index); the guard is skipped in that case, which is correct.