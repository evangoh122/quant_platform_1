# BUILD: #19 round 5 (MiMo)

DeepSeek (`.agents/deepseek/VERDICT-post-merge-round4.md`) ruled, and Claude agrees: a
**misconfiguration must be loud**. Only a TRANSIENT runtime failure of a correctly configured
embedder may degrade to BM25-only.

1. **Config errors raise.** In `api/services/embeddings.py:~176-185`, `get_embeddings()` must RAISE
   a clear `EmbeddingConfigError` (a subclass of `CorpusUnavailableError`, or mapped to it) instead
   of returning `None`, for:
   - provider `huggingface` without `HF_TOKEN`/`HUGGINGFACEHUB_API_TOKEN`;
   - an unknown provider;
   - a model the backend can't load.

   `search_sec_filings` → `retrieval_unavailable` with a message naming the missing setting, never
   the secret value. Read the provider, model and dim from config at call time, not as module-level
   import snapshots.
2. **Transient failures degrade.** A correctly configured embedder that raises at query time
   (network, timeout, 5xx) → `bm25_only` + `_warning="dense_unavailable"`. This keeps the round-4
   behaviour.
3. **Fix the test that passed for the wrong reason.** `TestEmbedderFailureDegradesToBM25Only` set
   `_embeddings_map = {}`, so `vector_search` returned early and never called the embedder. Load a
   NON-empty stored map, use an embedder whose `embed_query` raises, and assert it WAS called
   (counter). Mutation proof in /tmp: removing the `except` around the query embed must fail the test.
4. **End-to-end tests through `search_sec_filings`:**
   - missing token → `retrieval_unavailable`;
   - dimension mismatch → `retrieval_unavailable`;
   - model mismatch → `retrieval_unavailable`;
   - transient raise → `bm25_only` with the expected NVDA hit, respecting `as_of`.

Run `python3 -m pytest -q -p no:cacheprovider tests/rag tests/test_schema_env_override.py`, with and
without pyspark and databricks.connect hidden. LF line endings. Don't touch `.agents/dispatch.sh`.
Commit. Write `.agents/mimo/VERDICT-post-merge-round5.md`.
