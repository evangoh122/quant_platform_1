# BUILD: #19 round 3 (MiMo)

DeepSeek (`.agents/deepseek/VERDICT-post-merge-round2.md`): the dimension guard in
`api/services/hybrid_retriever.py:~501` compares the query vector with the CONFIGURED `EMBEDDING_DIM`,
not with the STORED index. Switching `EMBEDDING_PROVIDER=sentence_transformers` (1024-d) against the
stored 384-d index passes the guard. Then `np.dot` raises, and the search silently falls back to
substring search.

Fix:
- Record the index dimension when the corpus loads: the length of the stored vectors. Assert they are
  all the same length, else raise `CorpusUnavailableError`.
- Before scoring, compare `len(qvec)` with the STORED dimension. A mismatch raises
  `CorpusUnavailableError` with both numbers → `retrieval_unavailable`.
- Also: if `embedding_model` is stored in `gold_sec_chunk_embeddings`, check that it equals the
  active model. A mismatch → `CorpusUnavailableError`.
- Restore the sentence-transformers default to `BAAI/bge-small-en-v1.5` (384), so all defaults match
  the shipped index.

Tests, each failing on the current HEAD (prove it in /tmp):
- a 1024-d query against a 384-d stored index → `search_sec_filings` returns `retrieval_unavailable`,
  not `substring_fallback`;
- mixed stored dimensions → unavailable;
- a model-name mismatch → unavailable.

Run `python3 -m pytest -q -p no:cacheprovider tests/rag tests/test_schema_env_override.py`, with and
without pyspark and databricks.connect hidden. LF line endings. Don't touch `.agents/dispatch.sh`.
Commit. Write `.agents/mimo/VERDICT-post-merge-round3.md`.
