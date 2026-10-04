===VERDICT START===
# VERDICT: post-merge-round5 — DeepSeek (schema/API-contract lane)
**Status:** CHANGES_REQUESTED
**Round:** 5

Read-only check of commit `99a8e1f` ("fix: raise EmbeddingConfigError on
misconfiguration, fix embedder failure test"). Both round-4 blocking findings are
**fixed and mutation-proven** (see below). The config-vs-transient classification is
correct and the `retrieval_unavailable` status now fires. One new contract defect
keeps this from APPROVED: the error **message** returned to the caller is still
generic and misroutes the operator.

## Ruling on the deviation (message does not name the missing setting)

**It blocks.** The status is now correct (`retrieval_unavailable`, not `bm25_only`),
so the loudness requirement from round 4 is met. But the BUILD spec's acceptance
criterion was `retrieval_unavailable` **with a clear message** (test #2), and the
returned `message` is a hardcoded
`"SEC filing corpus could not be loaded. Check Delta table connectivity."` regardless
of the actual error. That is actively wrong: it sends the operator to check Delta
connectivity when the real fix is "set `HF_TOKEN`/`HUGGINGFACEHUB_API_TOKEN`". The
specific, secret-free message is already carried in the exception (verified via a live
probe: `EmbeddingConfigError` text names `HF_TOKEN` but is only written to the log,
then discarded at the boundary). The fix is trivial and low-risk — surface `str(e)`.

## Blocking findings

- [agent/tools_retrieval.py:121-128] The `except CorpusUnavailableError` handler returns
  the hardcoded message `"SEC filing corpus could not be loaded. Check Delta table
  connectivity."` and drops `str(e)`. Because `EmbeddingConfigError` subclasses
  `CorpusUnavailableError`, the missing-token / unknown-provider / model-mismatch cases
  all land here and lose the actionable message. → Concrete scenario:
  `EMBEDDING_PROVIDER=huggingface` with no token → `retrieval_unavailable` whose
  `message` tells the operator to check Delta connectivity, not to set `HF_TOKEN`.
  Probe (real handler, mocked retriever raising `EmbeddingConfigError`):
  `[{'error': 'retrieval_unavailable', 'message': 'SEC filing corpus could not be
  loaded. Check Delta table connectivity.', 'ticker': 'NVDA'}]`. The specific text
  ("...neither HF_TOKEN nor HUGGINGFACEHUB_API_TOKEN is set...") appears only in
  `logging.error`. This violates the spec's "clear message" criterion.

- [tests/rag/test_hybrid_retriever.py:2073] and
  [tests/rag/test_hybrid_retriever.py:2322] The assertion
  `"HF_TOKEN" in message or "SEC filing corpus" in message` is satisfied by the generic
  message, so both tests pass while the message does **not** name the setting. The
  `or "SEC filing corpus"` clause makes the "clear message" requirement untested (same
  class of green-for-the-wrong-reason defect as round-4 finding #3). → Removing the
  requirement entirely (keep only the generic message) leaves these tests green.

## Fixed round-4 findings (mutation-proven)

- Finding #1 (missing token degraded to BM25-only) → FIXED. `get_embeddings()` now
  raises `EmbeddingConfigError` for missing token / unknown provider / unloadable model
  (api/services/embeddings.py:181-198). Mutation: revert the missing-token branch to
  `return None` → `TestHuggingfaceWithoutToken::test_hf_no_token_raises_embedding_config_error`
  FAILS (`DID NOT RAISE EmbeddingConfigError`). Pin works.
- Finding #2 (raise path never exercised) → FIXED. `TestEmbedderFailureDegradesToBM25Only`
  now builds a non-empty `_embeddings_map` (so `vector_search` does not early-return) and
  asserts `call_count[0] > 0`. Mutation: delete the `except Exception` degrade block in
  `HybridRetriever.retrieve` → 4 of 5 tests in that class FAIL (the `RuntimeError` now
  propagates instead of degrading). Raise path is now genuinely exercised.

## config-vs-transient classification — correct

- `EmbeddingConfigError` subclasses `CorpusUnavailableError`; `retrieve()` re-raises
  `CorpusUnavailableError` (hybrid_retriever.py:646-648) and only degrades to BM25-only
  on a bare `Exception` (hybrid_retriever.py:649-652). So missing token / unknown
  provider / dim mismatch / model mismatch → `retrieval_unavailable`; a correctly
  configured embedder raising at query time → `bm25_only`/`dense_unavailable`. Matches
  the round-4 taxonomy.

## No secrets in messages — verified

`EmbeddingConfigError` texts name the setting (`HF_TOKEN`, `HUGGINGFACEHUB_API_TOKEN`,
`EMBEDDING_PROVIDER`) and the model name, never the token value. The query-time degrade
path logs only `type(e).__name__` and `str(e)` (no Authorization header). Clean.

## Non-blocking notes

- [api/services/embeddings.py:169-193] The `except Exception → EmbeddingConfigError`
  wrappers around `LocalSTEmbeddings(...)`/`HFInferenceEmbeddings(...)` are effectively
  unreachable: both constructors are lazy (no model load / no network in `__init__`).
  A local ST model whose weights are not cached fails at `embed_query` time and is
  classified as *transient* → BM25-only, not `retrieval_unavailable`. Acceptable per the
  current spec (spec only names "unloadable model at init"), but the "unloadable model is
  a config error" claim in the commit message is stronger than the code delivers.
- [tests/rag/test_hybrid_retriever.py:2286-2443] The new `TestEmbeddingE2EThroughSearchSecFilings`
  tests mock `HybridRetriever.retrieve` (via `side_effect`/`return_value`), so they verify
  the `search_sec_filings` error mapping, not the real `retrieve → vector_search →
  get_embeddings` path. Only `test_hf_no_token_raises_embedding_config_error` exercises the
  real `get_embeddings`. Recommend one true end-to-end test through the real retriever.
- [api/services/embeddings.py:25-27] `EMBEDDING_PROVIDER`/`ST_EMBEDDING_MODEL`/
  `EMBEDDING_DIM` remain module-level import-time snapshots while `vector_search` reads
  `_cfg.EMBEDDING_PROVIDER` dynamically. Pre-existing (carried from round 4).

## Checks run

```
$ python3 -m pytest -q -p no:cacheprovider tests/rag tests/test_schema_env_override.py
  → 302 passed, 19 skipped, 1 warning

$ PYTHONPATH=/tmp/ci_sim python3 -m pytest -q -p no:cacheprovider -p block_spark tests/rag tests/test_schema_env_override.py
  → 302 passed, 19 skipped, 1 warning   (pyspark + databricks.connect hidden)

$ # Mutation 1: missing-token branch → return None (revert raise)
$ python3 -m pytest -q tests/rag/test_hybrid_retriever.py::TestHuggingfaceWithoutToken
  → 1 failed (test_hf_no_token_raises_embedding_config_error: DID NOT RAISE), 1 passed  ✔

$ # Mutation 2: delete `except Exception` degrade block in HybridRetriever.retrieve
$ python3 -m pytest -q tests/rag/test_hybrid_retriever.py::TestEmbedderFailureDegradesToBM25Only
  → 4 failed, 1 passed   ✔ raise path exercised

$ # Live probe: search_sec_filings with retriever raising EmbeddingConfigError
$ PYTHONPATH=. python3 _scratch/probe_msg.py
  → message == "SEC filing corpus could not be loaded. Check Delta table connectivity."  ✘
    (HF_TOKEN named only in the log line, not in the returned message)

$ git diff --check 99a8e1f  → clean
```
===VERDICT END===
