===VERDICT START===
# VERDICT: post-merge-round4 — DeepSeek (schema/API-contract lane)
**Status:** CHANGES_REQUESTED
**Round:** 4

Read-only check of commit `ca929ec` ("fix: default EMBEDDING_PROVIDER to
sentence-transformers, degrade to BM25-only on embedder failure"). The default-provider
restore is correct and the stored-index dimension/model guard survives intact, but two
things keep this from APPROVED:

1. The missing-token misconfiguration is **not loud** — it degrades to BM25-only, which
   contradicts the BUILD spec (fix #1: "raise a clear config error at embedder init →
   `retrieval_unavailable`").
2. The new "embedder raises at query time" tests do **not** actually exercise the raise
   path — they short-circuit on an empty `_embeddings_map`, so the mutation criterion in
   the request ("remove the catch → the test fails") is false.

## Ruling on the deviation (missing-token → BM25-only)

**A tagged BM25-only answer is NOT acceptable for the missing-token case — this
misconfiguration must be loud, and it blocks.**

The commit establishes a three-bucket taxonomy, but mis-files the missing-token case:

| Bucket | Trigger | Required outcome | Implemented? |
| :-- | :-- | :-- | :-- |
| config error (loud) | dim/model mismatch | `retrieval_unavailable` | yes (`CorpusUnavailableError` re-raised) |
| config error (loud) | `huggingface` + no token | `retrieval_unavailable` | **no → BM25-only** |
| transient (degrade) | `embed_query()` raises at query time | `bm25_only` | yes |

`EMBEDDING_PROVIDER=huggingface` is an **explicit opt-in**. A user who sets it and omits
`HF_TOKEN`/`HUGGINGFACEHUB_API_TOKEN` has a *static* misconfiguration that will never
self-resolve — it is the same class of error as the dimension/model mismatch, not a
transient network/auth failure. Silently serving lexical-only results (with only a hidden
`_warning` in result metadata) masks a broken config and defeats the spec's intent that
the agent report the failure. Verified at runtime: with a non-empty dense index and
`EMBEDDING_PROVIDER=huggingface` + no token, `get_embeddings()` returns `None`,
`vector_search` returns `[]`, and `retrieve` returns `('bm25_only', 'dense_unavailable')`
— never `retrieval_unavailable`.

**Recommendation:** at embedder init, when provider is `huggingface` and no token is set,
raise (or map to `CorpusUnavailableError`) so `search_sec_filings` surfaces
`retrieval_unavailable` with the clear message already logged at
`api/services/embeddings.py:180-184`. Reserve BM25-only for the genuine transient path
(`embed_query()` raising). This means `get_embeddings()` returning `None` for *any*
init-time reason (missing token, ST init failure, unsupported provider) should be treated
as a config error, not "dense skipped".

## Blocking findings

- [api/services/embeddings.py:176-185] `get_embeddings()` returns `None` (logs only) when
  `huggingface` has no token, instead of raising a config error. → A user opting into
  `huggingface` without a token silently gets `bm25_only` results, never the
  `retrieval_unavailable` the spec mandates. Concrete scenario: `EMBEDDING_PROVIDER=
  huggingface`, no token → 5 results tagged `bm25_only`/`dense_unavailable`, no
  structured error surfaced to the caller.

- [tests/rag/test_hybrid_retriever.py:2016-2053] The
  `TestEmbedderFailureDegradesToBM25Only` autouse fixture sets `_embeddings_map = {}`,
  and `vector_search` short-circuits at `hybrid_retriever.py:525-526` (`if not
  _embeddings_map: return []`) *before* ever calling `get_embeddings()`/`embed_query()`.
  → `FailingEmbeddings.embed_query` is never invoked, so the tests pass via the
  empty-map path, not the raise path. Verified by mutation: removing the `except
  Exception` catch in `retrieve()` leaves the **full suite green (297 passed)** — the
  raise→BM25-only behavior is untested. The request's mutation criterion is not met.

- [tests/rag/test_hybrid_retriever.py:2032-2068]
  `test_hf_no_token_search_sec_filings_returns_unavailable` mocks
  `HybridRetriever.retrieve` to raise `CorpusUnavailableError`, so it asserts the
  *intended* contract while the real path does not implement it (see finding #1). It is
  green for the wrong reason and would not catch the actual deviation.

## Non-blocking notes

- [api/services/embeddings.py:24-26] `EMBEDDING_PROVIDER`/`ST_EMBEDDING_MODEL`/
  `EMBEDDING_DIM` are module-level snapshots read at import, while `vector_search` now
  reads `_cfg.EMBEDDING_PROVIDER` dynamically (`hybrid_retriever.py:545`). If env changes
  after import the two views diverge. Pre-existing, but the round-4 change makes the
  split more visible.
- [api/services/embeddings.py:168-197] `get_embeddings()` conflates three distinct
  init-time failures (missing token / ST init failure / unsupported provider) into a
  single `return None`. All three are config errors and, under the ruling above, should
  be loud rather than silent dense-skip.
- `test_dimension_mismatch_still_returns_unavailable` exercises `vector_search` directly;
  there is no end-to-end test that `search_sec_filings` surfaces `retrieval_unavailable`
  for a live dim/model mismatch (the code path is correct: `retrieve` re-raises
  `CorpusUnavailableError` → `search_sec_filings:121-127`).

## Checks run

```
$ python3 -m pytest -q -p no:cacheprovider tests/rag tests/test_schema_env_override.py
  → 297 passed, 19 skipped, 1 warning

$ # pyspark + databricks.connect hidden (sys.meta_path ImportError blocker)
$ PYTHONPATH=/tmp/ci_sim python3 -m pytest -q -p no:cacheprovider -p block_spark tests/rag tests/test_schema_env_override.py
  → 297 passed, 19 skipped, 1 warning

$ # Mutation: default EMBEDDING_PROVIDER "sentence-transformers" → "huggingface"
$ python3 -m pytest -q tests/rag/test_hybrid_retriever.py::TestDefaultEmbeddingProvider
  → 1 failed (test_default_provider_is_sentence_transformers), 2 passed  ✔ pin works

$ # Mutation: remove the except Exception (raise) catch in HybridRetriever.retrieve
$ python3 -m pytest -q tests/rag tests/test_schema_env_override.py
  → 297 passed, 19 skipped   ✘ NO test fails → raise path untested

$ # Live probe: huggingface + no token, NON-EMPTY embeddings map
$ python3 /tmp/probe2.py
  → get_embeddings() -> None ; retrieve -> [('bm25_only', 'dense_unavailable')]  ✘ not retrieval_unavailable

$ git diff --check ca929ec  → clean
```
===VERDICT END===
