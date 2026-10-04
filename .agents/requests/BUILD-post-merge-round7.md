# BUILD: #19 round 7, Codex review (MiMo)

Read `.agents/codex/VERDICT-post-merge-round6.md`. In `api/services/hybrid_retriever.py:~527` and
`~541`, the dimension mismatch and model mismatch raise plain `CorpusUnavailableError`. So
`search_sec_filings` returns the generic corpus message with no `reason: embedding_config`. Both are
configuration errors.

Fix:
- Raise `EmbeddingConfigError` for both. Each message names the setting and both values, e.g. "query
  embedding dim 1024 != stored index dim 384; check EMBEDDING_PROVIDER / ST_EMBEDDING_MODEL /
  EMBEDDING_DIM", and likewise for a model mismatch. No secret values.
- Mixed stored dimensions stay a corpus error (plain `CorpusUnavailableError`). That one is a data
  problem, not config.
- Tightened tests at `tests/rag/test_hybrid_retriever.py:~2355` and `~2379`: assert
  `reason == "embedding_config"`, that the setting name is in the message, and that "Delta" is not in
  the message. Prove in /tmp that the tightened tests fail on the current HEAD.

Run `python3 -m pytest -q -p no:cacheprovider tests/rag tests/test_schema_env_override.py`, with and
without pyspark and databricks.connect hidden. LF line endings. Don't touch `.agents/dispatch.sh`.
Leave no scratch files. Commit with a descriptive message. Write `.agents/mimo/VERDICT-post-merge-round7.md`.
