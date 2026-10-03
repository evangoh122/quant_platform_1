===CODEX VERDICT START===

CHANGES_REQUESTED

Blocking finding:

- [api/services/hybrid_retriever.py:527](/home/jianj/code/qp1-fix/api/services/hybrid_retriever.py:527) and [api/services/hybrid_retriever.py:541](/home/jianj/code/qp1-fix/api/services/hybrid_retriever.py:541) raise plain `CorpusUnavailableError` for dimension/model mismatches. Consequently, [agent/tools_retrieval.py:135](/home/jianj/code/qp1-fix/agent/tools_retrieval.py:135) returns the generic corpus message without `reason: embedding_config`. This violates the stated requirement that dimension/model configuration errors return `retrieval_unavailable`, `reason: embedding_config`, and a message naming the relevant setting.
- The tests at [tests/rag/test_hybrid_retriever.py:2355](/home/jianj/code/qp1-fix/tests/rag/test_hybrid_retriever.py:2355) and [tests/rag/test_hybrid_retriever.py:2379](/home/jianj/code/qp1-fix/tests/rag/test_hybrid_retriever.py:2379) only assert `retrieval_unavailable`; they do not assert `reason` or the actionable message, allowing this regression.

Validation completed:

- DeepSeek round-6 verdict: APPROVED.
- Full suite stalled silently for over one minute and was stopped per instructions.
- Focused suite: `303 passed, 19 skipped`.
- Focused suite with Databricks Connect and PySpark hidden: `303 passed, 19 skipped`.
- CI checks passed: every `uses:` is pinned to a 40-hex SHA, every checkout disables persisted credentials, and `start_app` defaults to `false`.
- Repository remained unmodified.

Mutation proofs successfully failed tests for:

- BM25 ticker filter removal.
- `_corpus_loaded=True` after failure.
- Query/stored dimension guard removal, including 1024-d sentence-transformers output against a 384-d index.
- Blind `except Exception` restoration in `build_sec_embeddings`.
- `--schema` FQN rebind removal.
- Local default-provider pin removal.
- Transient embedder fallback removal; the embedder was reached.
- `embedding_config` handler removal.
- Secret-safe message removal.
- Mixed stored-dimension guard removal.

===CODEX VERDICT END===
