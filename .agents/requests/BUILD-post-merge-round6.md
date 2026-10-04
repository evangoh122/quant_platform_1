# BUILD: #19 round 6 (MiMo)

DeepSeek (`.agents/deepseek/VERDICT-post-merge-round5.md`):
1. `agent/tools_retrieval.py:~121-128` returns a hardcoded "Check Delta table connectivity" message
   for EVERY `CorpusUnavailableError`, including `EmbeddingConfigError`, which drops the actionable
   text.
   - For `EmbeddingConfigError`, return its own message. It names the missing setting, e.g.
     "EMBEDDING_PROVIDER=huggingface requires HF_TOKEN or HUGGINGFACEHUB_API_TOKEN". It must NEVER
     include a secret VALUE. Set `"error": "retrieval_misconfigured"`, or keep
     `retrieval_unavailable` and add `"reason": "embedding_config"`; pick one and document it.
   - Keep the generic corpus message ONLY for real corpus/Delta load failures.
2. Tests at `tests/rag/test_hybrid_retriever.py:~2073` and `~2322` assert
   `"HF_TOKEN" in message or "SEC filing corpus" in message`. The `or` makes them pass for the
   wrong reason. Assert the exact setting name is present, and the Delta text is ABSENT for config
   errors. Add a test that a set token's value never appears in the message.

Prove in /tmp that each new or changed test fails on the current HEAD. Run
`python3 -m pytest -q -p no:cacheprovider tests/rag tests/test_schema_env_override.py`, with and
without pyspark and databricks.connect hidden. LF line endings. Don't touch `.agents/dispatch.sh`.
Leave NO scratch files in the repo. Commit with a descriptive message. Write
`.agents/mimo/VERDICT-post-merge-round6.md`.
