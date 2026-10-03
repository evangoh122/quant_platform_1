# CHECK: #19 round 4 (DeepSeek)

Commit ca929ec:
- restores the local default `EMBEDDING_PROVIDER=sentence-transformers` (bge-small, 384), which
  fixes the live regression Claude found (the remote HF API → 401 → substring → `[]`);
- degrades to BM25-only when the embedding fails at query time.

Read `.agents/requests/BUILD-post-merge-round4.md`. Read-only. Write
`.agents/deepseek/VERDICT-post-merge-round4.md` (===VERDICT START/END===, Status).

Claude's live results:
- default → 5 hybrid NVDA results, filing accepted 2024-11-20 (`as_of` 2025-01-01 respected);
- `EMBEDDING_PROVIDER=huggingface` with no token → 5 results tagged `bm25_only`. The spec said
  "→ `retrieval_unavailable` with a clear message".

Rule on this deviation. Is a tagged BM25-only answer acceptable, or must a missing-token
misconfiguration be loud? Recommend one, with reasons, and say whether it blocks.

Check:
- The BM25-only path still applies the point-in-time and ticker filters BEFORE scoring, and
  reranks.
- The dimension or model mismatch is still `retrieval_unavailable`, not BM25-only.
- The test pinning the default provider fails if the default changes (mutation).
- An embedder raising at query time → `bm25_only` with the expected hit (mutation: remove the
  catch → the test fails).

Run `python3 -m pytest -q -p no:cacheprovider tests/rag tests/test_schema_env_override.py`, with and
without pyspark and databricks.connect hidden.
