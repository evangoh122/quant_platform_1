# VERDICT: post-merge-round2 — MiMo
**Status:** APPROVED
**Round:** 1

## Summary

Fixed config/implementation mismatch where `api/config.py` reported `Qwen/Qwen3-Embedding-8B` (4096-d) while `api/services/embeddings.py` actually used `BAAI/bge-small-en-v1.5` (384-d). Config is now the single source of truth.

## Fixes applied

1. **`api/config.py:178`** — `HF_EMBEDDING_MODEL` default changed from `Qwen/Qwen3-Embedding-8B` to `BAAI/bge-small-en-v1.5`.

2. **`api/config.py:210-211`** — `EMBEDDING_DIM` for huggingface provider changed from `4096` to `384`.

3. **`api/services/embeddings.py:20-27`** — Replaced hardcoded `EMBEDDING_PROVIDER`, `ST_EMBEDDING_MODEL`, `EMBEDDING_DIM`, `EMBEDDING_QUERY_PREFIX` with imports from `api.config`.

4. **`api/services/embeddings.py:174`** — `HFInferenceEmbeddings` now uses `config.HF_EMBEDDING_MODEL` instead of `os.getenv(...)`.

5. **`tests/rag/test_embedding_config.py`** — 6 new tests verifying config/embeddings consistency.

## Regression tests (6 new)

| Test | What it verifies |
|:--|:--|
| `test_config_hf_model_default` | config.HF_EMBEDDING_MODEL == "BAAI/bge-small-en-v1.5" |
| `test_config_embedding_dim_hf_provider` | config.EMBEDDING_DIM == 384 |
| `test_embeddings_dim_matches_config` | embeddings.EMBEDDING_DIM == config.EMBEDDING_DIM == 384 |
| `test_embeddings_provider_matches_config` | embeddings.EMBEDDING_PROVIDER == config.EMBEDDING_PROVIDER |
| `test_st_model_matches_config` | embeddings.ST_EMBEDDING_MODEL == config.ST_EMBEDDING_MODEL |
| `test_hybrid_retriever_uses_config_dim` | hybrid_retriever.EMBEDDING_DIM == config.EMBEDDING_DIM == 384 |

## Checks run

- `python3 -m pytest -q -p no:cacheprovider tests/rag tests/test_schema_env_override.py` → **283 passed, 19 skipped** (8.48s)
- `PYTHONPATH=/tmp/nopyspark python3 -m pytest -q -p no:cacheprovider tests/rag tests/test_schema_env_override.py` → **283 passed, 19 skipped** (6.05s)

## Files changed

- `api/config.py` — single source of truth for HF model and embedding dim
- `api/services/embeddings.py` — imports config values instead of hardcoding
- `tests/rag/test_embedding_config.py` — new consistency tests