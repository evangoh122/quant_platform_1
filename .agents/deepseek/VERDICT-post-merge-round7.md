===VERDICT START===
# VERDICT: post-merge-round7 — DeepSeek (schema/API-contract lane)
**Status:** APPROVED
**Round:** 7

Read-only check of commit `f8570bf` ("fix: raise EmbeddingConfigError for dim/model
mismatch with user_safe flag"). Codex's round-6 finding is **fixed and mutation-proven**.
The dim/model mismatch now returns `reason: "embedding_config"` with an actionable
setting-named message (no "Delta"), mixed stored dims stay a corpus error, and the
`user_safe` flag is safe-by-default with no secret-leak path. No new defects found.

## Round-6 finding — fixed (mutation-proven)

Codex: `vector_search` raised plain `CorpusUnavailableError` for dim/model mismatch, so
`search_sec_filings` returned the generic corpus message (no `reason`, no setting name).

- **`hybrid_retriever.py:528` (dim) and `:543` (model) now raise `EmbeddingConfigError`**
  with `user_safe=True` and messages naming `EMBEDDING_PROVIDER / ST_EMBEDDING_MODEL /
  EMBEDDING_DIM`. Live probe through the **real** `vector_search → search_sec_filings` path
  (not the mocked `retrieve`) confirms:
  - dim mismatch → `{'error':'retrieval_unavailable','reason':'embedding_config','message':'query embedding dim 1024 != stored index dim 384; check EMBEDDING_PROVIDER / ST_EMBEDDING_MODEL / EMBEDDING_DIM', ...}` — no "Delta".
  - model mismatch → `{'error':'retrieval_unavailable','reason':'embedding_config','message':"embedding model mismatch: active 'BAAI/bge-small-en-v1.5' != stored 'OLD-MODEL'; check EMBEDDING_PROVIDER / ST_EMBEDDING_MODEL", ...}` — no "Delta".

## Mixed stored dims stay a corpus error — verified

`_load_corpus` (`hybrid_retriever.py:296-300`) still raises a **plain**
`CorpusUnavailableError` ("Embedding dimension mismatch in stored index…") for mixed stored
dims. It is NOT an `EmbeddingConfigError`, so `search_sec_filings` routes it to the generic
corpus handler (no `reason` key). Pinned by `test_mixed_stored_dimensions_unavailable`
(`pytest.raises(CorpusUnavailableError, match="dimension mismatch")`).

## `user_safe` semantics and secret-leak analysis

- `EmbeddingConfigError(*args, user_safe=False)` (`exceptions.py:30`) — **safe by default**.
- `search_sec_filings` (`tools_retrieval.py:125-131`): `user_safe=True` → pass `str(e)`;
  otherwise → hardcoded constant. The hardcoded message names env-var *names*, never values.
- The only two `user_safe=True` call sites are the dim/model mismatch errors, whose messages
  interpolate only integers (dims) and model names — no secret material.
- Missing-token / unknown-provider / model-load errors are raised **without** `user_safe`, so
  they collapse to the hardcoded message. A token value can never reach the caller.
- **Mutation proof (leak):** changing the handler to `safe_msg = str(e)` unconditionally →
  `test_token_value_never_leaks_in_message` FAILS (`hf_FAKE_TOKEN_VALUE_12345` leaked). Guard is real.
- **Mutation proof (passthrough):** removing the `user_safe` branch (always hardcoded) →
  `test_model_mismatch_returns_retrieval_unavailable` FAILS (`ST_EMBEDDING_MODEL` absent from
  hardcoded message). The tightened assertion is load-bearing, not satisfiable by the generic text.

## Tightened tests fail on the previous HEAD — proven in /tmp

Checked out `7a74215` (parent of `f8570bf`) to `/tmp/qp1_prev`, overlaid the NEW test file:

```
$ python3 -m pytest -q '...test_dimension_mismatch_returns_retrieval_unavailable' \
                       '...test_model_mismatch_returns_retrieval_unavailable'
→ 2 failed
  test_dimension_mismatch…  AssertionError (len(result) == 1 → 5, substring fallback)
  test_model_mismatch…      AssertionError (len(result) == 1 → 5, substring fallback)
```

The old `EmbeddingConfigError` accepted no `user_safe` kwarg, so the tightened tests error out
into the substring fallback on the old HEAD — proving they cannot pass green on the regressed code.

## Round-5 findings — still fixed (no `or`-clause regression)

- **Generic-corpus-message-for-config-errors** remains fixed: the dedicated
  `except EmbeddingConfigError` block precedes `except CorpusUnavailableError`
  (`tools_retrieval.py:122` vs `:138`).
- **No `or`-clause** survives: grep for `in msg.*or.*msg` / `HF_TOKEN.*or.*SEC` returns nothing.
  The dim/model assertions (`"EMBEDDING_PROVIDER" in msg` / `"ST_EMBEDDING_MODEL" in msg` /
  `"Delta" not in msg`) are conjunctive, not `or`.
- **Real Delta failures keep the corpus message:** `test_returns_structured_error_on_corpus_unavailable`,
  `test_unavailable_result_contains_no_exception_text`, and the mixed-dims pin all hold.

## Non-blocking notes

- The E2E dim/model tests (`TestEmbeddingE2EThroughSearchSecFilings`) mock
  `HybridRetriever.retrieve`, so the real `vector_search → EmbeddingConfigError` raising path is
  not directly asserted by a unit test. It IS correct in code (verified by live probe above), but a
  future refactor of the raise-site could silently regress `reason` while the mocked E2E tests stay
  green. Recommend a follow-up test that drives the real `vector_search` path through
  `search_sec_filings` (like the probe) rather than mocking `retrieve`.
- `user_safe` relies on developer discipline to keep `True` only for secret-free messages. It is
  safe today; a comment (already present in `exceptions.py`) is the only guard against a future
  `user_safe=True` on a message that interpolates a token.

## Checks run

```
$ python3 -m pytest -q -p no:cacheprovider tests/rag tests/test_schema_env_override.py
  → 303 passed, 19 skipped, 1 warning

$ PYTHONPATH=/tmp/ci_sim python3 -m pytest -q -p no:cacheprovider -p block_spark tests/rag tests/test_schema_env_override.py
  → 303 passed, 19 skipped, 1 warning   (pyspark + databricks.connect hidden)

$ python3 -m pytest -q '...TestEmbeddingDimCheck' '...TestStoredIndexDimensionGuard' \
                       '...TestEmbeddingE2EThroughSearchSecFilings' '...TestHuggingfaceWithoutToken'
  → 13 passed

$ # previous-HEAD proof (worktree /tmp/qp1_prev @ 7a74215 + new test file)
$ python3 -m pytest -q '...test_dimension_mismatch_returns_retrieval_unavailable' \
                       '...test_model_mismatch_returns_retrieval_unavailable'
  → 2 failed   ✔ tightened tests are load-bearing

$ # mutation: safe_msg = str(e)  → test_token_value_never_leaks_in_message
  → 1 failed (secret leaked)   ✔ no-secret guard holds

$ # mutation: remove user_safe branch  → test_model_mismatch_returns_retrieval_unavailable
  → 1 failed (ST_EMBEDDING_MODEL missing)   ✔ passthrough is load-bearing

$ # live probe (real vector_search → search_sec_filings): dim + model mismatch
  → both return reason=embedding_config, setting-named message, no 'Delta'   ✔

$ git status → clean (worktrees removed, no mutation left in repo)
```
===VERDICT END===
