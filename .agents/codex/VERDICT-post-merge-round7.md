===CODEX VERDICT START===
APPROVED

- DeepSeek round-7 verdict: APPROVED.
- Reviewed `git diff origin/main -- . ':!.agents'`; no blocking defects found.
- Round-6 finding is fixed:
  - Dimension/model mismatches raise `EmbeddingConfigError(user_safe=True)` at `api/services/hybrid_retriever.py:527` and `:542`.
  - They surface as `retrieval_unavailable` with `reason: embedding_config` at `agent/tools_retrieval.py:122`.
  - Unsafe errors receive a constant redacted message; `user_safe` defaults to false at `api/services/exceptions.py:30`.
- Default provider/model/dimension are consistently local sentence-transformers, BGE-small, and 384 at `api/config.py:173-210`.
- Mixed stored dimensions remain unavailable at `api/services/hybrid_retriever.py:295-301`.
- Transient query-time embedder failures degrade to BM25-only at `api/services/hybrid_retriever.py:641-654`.
- CI check passed:
  - Every `uses:` reference is a 40-hex SHA.
  - Every checkout has `persist-credentials: false`.
  - `start_app` defaults to `false`.

Test results:

- The requested full suite stalled without output in this sandbox.
- Requested fallback suite reached 100% in both normal and dependency-hidden modes without failures, but teardown did not exit.
- Focused regression baseline completed normally:
  - Normal: `38 passed`
  - `databricks.connect` and `pyspark` hidden: `38 passed`

Mutation proofs—all produced at least one failure:

- Remove BM25 ticker filter: 3 failed.
- Set `_corpus_loaded=True` after failure: 1 failed.
- Remove query-dimension guard: 2 failed.
- Restore blind `except` in `build_sec_embeddings`: 1 failed.
- Remove `--schema` FQN rebind: 1 failed.
- Remove mixed-stored-dimension guard: 1 failed.
- Change default provider back to Hugging Face: 1 failed.
- Propagate transient embedder failure instead of BM25-only: 1 failed; embedder call was reached.
- Remove `embedding_config` classification: 1 failed.
- Surface unsafe exception text: secret-leak test failed.
- Remove `user_safe` passthrough: tightened model-mismatch test failed.

Repository remained unmodified and clean.
===CODEX VERDICT END===
