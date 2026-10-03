# CHECK: #19 round 4 (DeepSeek)

Commit ca929ec:
- restores the local default `EMBEDDING_PROVIDER=sentence-transformers` (bge-small, 384), which
  fixes the live regression Claude found (the remote HF API → 401 → substring → `[]`);
- degrades to BM25-only when the embedding fails at query time.

Read `.agents/requests/BUILD-post-merge-round4.md`. Read-only. Write
`.agents/deepseek/VERDICT-post-merge-round5.md` (===VERDICT START/END===, Status).

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

## Re-check after round 5 (this run)
Commit 99a8e1f: config errors raise `EmbeddingConfigError`, and the embedder-failure test is fixed.
Claude's live results:
- default → 5 hybrid results (2024-11-20);
- `EMBEDDING_PROVIDER=huggingface` with no token → `retrieval_unavailable`, BUT the message reads
  "SEC filing corpus could not be loaded. Check Delta table connectivity." The spec required the
  message to NAME the missing setting. Does this block? It sends an operator to the wrong place.

Verify:
- your two round-4 findings are fixed, with the mutation proofs;
- config vs transient classification;
- no secret values in any message;
- the end-to-end tests.

Write `.agents/deepseek/

## Re-check after round 6 (this run)
Commit df1deaf surfaces config errors with `reason: "embedding_config"`. Claude's live run, with
huggingface and no token:
`{'error': 'retrieval_unavailable', 'reason': 'embedding_config', 'message': 'Embedding
configuration error — check EMBEDDING_PROVIDER, HF_TOKEN, or HUGGINGFACEHUB_API_TOKEN settings.'}`

Verify:
- both of your round-5 findings, including that the tests no longer pass via an `or` clause;
- a token's value never appears in the message;
- real Delta failures keep the corpus message.

Write `.agents/deepseek/VERDICT-post-merge-round6.md`.

## Re-check after round 7 (this run)
Codex's review (`.agents/codex/VERDICT-post-merge-round6.md`): the dim/model mismatch raised a plain
`CorpusUnavailableError`, which loses `reason: embedding_config`. Commit f8570bf raises
`EmbeddingConfigError`, with a `user_safe` flag.

Verify:
- the dim and model mismatch → `reason: embedding_config`, a message naming the setting, no "Delta";
- mixed stored dims stay a corpus error;
- the tightened tests fail on the previous HEAD (prove it in /tmp);
- what `user_safe` does, and whether it could ever leak a secret into the message.

Write `.agents/deepseek/VERDICT-post-merge-round7.md`.
