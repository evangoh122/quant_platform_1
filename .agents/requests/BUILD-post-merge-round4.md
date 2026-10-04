# BUILD: #19 round 4, live regression found by Claude's review (MiMo)

DeepSeek and Codex both approved round 3, but Claude's LIVE search returns `[]`:

    provider huggingface  model BAAI/bge-small-en-v1.5  dim 384
    POST router.huggingface.co/.../feature-extraction -> 401 Unauthorized
    ... Failed to resolve api-inference.huggingface.co
    Hybrid retriever failed (...), falling back to substring filter
    RESULT []

Root cause: round 2 made `api/config.py` the source of truth, and its `EMBEDDING_PROVIDER` default is
`"huggingface"`, the REMOTE HF Inference API, which needs a token. On origin/main the default was
`"sentence-transformers"` (local), which is how `pipelines/build_sec_embeddings.py` built the stored
index. The unit tests mock the embeddings, so none of them caught it.

## Fixes
1. **The default provider is local.** Change the `api/config.py` default to `EMBEDDING_PROVIDER=
   "sentence-transformers"`, with model `BAAI/bge-small-en-v1.5`, dim 384, matching main and the
   stored index. Keep `huggingface` as an explicit opt-in that requires a token: if the provider is
   huggingface and no `HF_TOKEN`/`HUGGINGFACEHUB_API_TOKEN` is set, raise a clear config error at
   embedder init → `retrieval_unavailable`.
2. **An embedding failure degrades to BM25-only, not substring.** If the query embedding fails at
   runtime (network, auth, any error), the dense half is unavailable but BM25 still works locally.
   - In `HybridRetriever.retrieve`, catch the embedder failure: run BM25 only (still filtered by
     point-in-time and ticker), then rerank. Tag the results `retrieval_mode="bm25_only"` and
     `_warning="dense_unavailable"`.
   - Keep the substring fallback only for corpus-level failures where BM25 can't run either.
   - The dimension or model mismatch from round 3 must still return `retrieval_unavailable`. It is a
     configuration error, not a transient one.
3. **Tests**, each failing on the current HEAD (prove it in /tmp):
   - with no env, `config.EMBEDDING_PROVIDER == "sentence-transformers"`;
   - provider huggingface without a token → `retrieval_unavailable` with a clear message;
   - an embedder that raises at query time → results come back with `retrieval_mode == "bm25_only"`,
     contain the expected BM25 hit, and respect `as_of` and the ticker;
   - the dimension mismatch is still `retrieval_unavailable`.

Run `python3 -m pytest -q -p no:cacheprovider tests/rag tests/test_schema_env_override.py`, with and
without pyspark and databricks.connect hidden. LF line endings. Don't touch `.agents/dispatch.sh`.
Commit. Write `.agents/mimo/VERDICT-post-merge-round4.md`. Claude will rerun the live search.
