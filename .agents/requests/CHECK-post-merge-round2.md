# CHECK: #19 round 2 (DeepSeek)

Commit 08fed84 makes `api/config.py` the single source of truth for the HF embedding model and the
embedding dimension. This addresses the Codex review in `.agents/codex/VERDICT-post-merge-coderabbit.md`.
Read-only. Write `.agents/deepseek/VERDICT-post-merge-round3.md` (===VERDICT START/END===, Status).

Check:
- Is there one source of truth now? `embeddings.py`, `hybrid_retriever.EMBEDDING_DIM` and
  `api/config.py` must agree (384, bge-small).
- What about other providers? Which model and dimension does `EMBEDDING_PROVIDER=sentence_transformers`
  give, and does the stored 384-d index still produce a clean `retrieval_unavailable` there (not a
  silent fallback)?
- Env overrides: `HF_EMBEDDING_MODEL` and `EMBEDDING_DIM`.
- The new test fails when either constant is mutated (prove it in /tmp).
- Nothing else regressed.

Run, both with and without pyspark and databricks.connect hidden:
`python3 -m pytest -q -p no:cacheprovider tests/rag tests/test_schema_env_override.py`

## Re-check after round 3 (this run)
Commit 792e746 validates the query dimension against the STORED index dimension, checks the stored
model name, and restores the sentence-transformers default to bge-small (384). Re-verify your blocking
finding: `EMBEDDING_PROVIDER=sentence_transformers` with a 1024-d model against the 384-d index →
`retrieval_unavailable`, not `substring_fallback`. Mixed stored dimensions → unavailable.
Write `.agents/deepseek/VERDICT-post-merge-round3.md`.
