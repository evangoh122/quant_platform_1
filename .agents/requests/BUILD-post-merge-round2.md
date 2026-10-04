# BUILD: post-merge fixes round 2 (MiMo)

Codex review (`.agents/codex/VERDICT-post-merge-coderabbit.md`) found one blocking issue.

`api/services/embeddings.py:~175` now defaults the HuggingFace model to `BAAI/bge-small-en-v1.5`
(384-d), but `api/config.py:~178` still reports `Qwen/Qwen3-Embedding-8B` and `api/config.py:~210-211`
still reports 4096 dimensions. The config/telemetry disagrees with the real implementation.

Fix:
- Make `api/config.py` the single source of truth for the HF default model name and the embedding
  dimension (384 for bge-small).
- `api/services/embeddings.py` must import those values, not hardcode its own default.
- `EMBEDDING_DIM` used by `hybrid_retriever` must equal the config value.
- Test: config model == embeddings default; config dim == `EMBEDDING_DIM` == 384. Mutating either
  constant fails the test (prove it in /tmp).

Run `python3 -m pytest -q -p no:cacheprovider tests/rag tests/test_schema_env_override.py`. Run it
again with pyspark and databricks.connect hidden, via a sitecustomize that sets `sys.modules[m]=None`
for databricks.connect, pyspark, pyspark.sql, pyspark.sql.functions and pyspark.sql.types.

LF line endings. Don't touch `.agents/dispatch.sh`. Commit. Write
`.agents/mimo/VERDICT-post-merge-round2.md`.
