===VERDICT START===
# VERDICT: post-merge-round6 — DeepSeek (schema/API-contract lane)
**Status:** APPROVED
**Round:** 6

Read-only check of commit `df1deaf` ("fix: surface EmbeddingConfigError message instead
of generic corpus error"). Both round-5 findings are **fixed and mutation-proven**. The
`reason: "embedding_config"` contract is correctly scoped, the secret-free message names the
missing setting, and the token value cannot reach the caller. The deviation Claude flagged in
round 5 is resolved; no new defects found.

## Ruling on the round-5 deviation

**No longer blocks.** Round 5's blocking finding was that `search_sec_filings` caught
`EmbeddingConfigError` through its `CorpusUnavailableError` superclass handler and returned the
generic `"SEC filing corpus could not be loaded. Check Delta table connectivity."` message. The
round-6 fix inserts a dedicated `except EmbeddingConfigError` handler *before*
`except CorpusUnavailableError` (agent/tools_retrieval.py:122-134) that returns
`{'error':'retrieval_unavailable','reason':'embedding_config','message':'Embedding
configuration error — check EMBEDDING_PROVIDER, HF_TOKEN, or HUGGINGFACEHUB_API_TOKEN
settings.'}`. The message names the missing setting (not the token value), so the operator is
routed to the right place. It does not use `str(e)` for the returned message — the raw exception
text goes only to `logging.error` — so the token value can never leak even if it happened to
appear in the exception.

## Round-5 findings — fixed (mutation-proven)

- **Finding #1 (generic corpus message for config errors) → FIXED.** The dedicated
  `EmbeddingConfigError` handler returns the actionable `reason: "embedding_config"` message.
  Mutation proof: deleting the `except EmbeddingConfigError` block →
  `TestHuggingfaceWithoutToken::test_hf_no_token_search_sec_filings_returns_unavailable` and
  `TestEmbeddingE2EThroughSearchSecFilings::test_missing_token_returns_retrieval_unavailable`
  both FAIL (`Expected 'HF_TOKEN' in message, got: SEC filing corpus could not be loaded…`).

- **Finding #2 (`or "SEC filing corpus"` clause let tests pass green-for-wrong-reason) → FIXED.**
  Both assertions now require `"HF_TOKEN" in msg` and `"SEC filing corpus" not in msg`
  (test_hybrid_retriever.py:2074-2075 and 2325-2326). No `or` clause remains anywhere in the
  suite (grep confirms). The mutation proof above doubles as the proof here: with the config
  handler removed, the "HF_TOKEN must be named" assertion genuinely fails, so the test is no
  longer satisfiable by the generic message.

## No-secret guarantee — verified

- The returned message is a hardcoded constant; `str(e)` is written only to `logging.error`.
- New test `test_token_value_never_leaks_in_message` (test_hybrid_retriever.py:2328-2353) raises
  an `EmbeddingConfigError` whose text deliberately embeds `hf_FAKE_TOKEN_VALUE_12345` and
  asserts it is absent from the returned message.
  Mutation proof: changing `safe_msg` to `str(e)` in the handler →
  `test_token_value_never_leaks_in_message` FAILS
  (`Secret token value leaked into message: … Got: hf_FAKE_TOKEN_VALUE_12345`). The guard is real.

## Real Delta failures keep the corpus message — verified

- A plain `CorpusUnavailableError` (not an `EmbeddingConfigError` subclass) still lands in the
  generic handler. Live probe with `retrieve()` raising `CorpusUnavailableError("Delta table
  unreachable")` → `{'error':'retrieval_unavailable','message':'SEC filing corpus could not be
  loaded. Check Delta table connectivity.','ticker':'NVDA'}` with **no** `reason` key. Correct:
  only config errors get `reason: "embedding_config"`.
- Pin tests already cover this: test_hybrid_retriever.py:1195-1218 and 1449-1454 assert the
  corpus message and (line 1454) that raw exception text does not leak.

## config-vs-transient classification — unchanged and correct

- `EmbeddingConfigError(CorpusUnavailableError)` → `retrieval_unavailable` (loud). Missing token
  / unknown provider / dim or model mismatch all classified as config errors. A correctly
  configured embedder raising at query time still degrades to `bm25_only`/`dense_unavailable`
  (transient), per hybrid_retriever.py's bare-`Exception` degrade path. Matches the round-4
  taxonomy; unchanged by this commit.

## Non-blocking notes

- [api/services/embeddings.py:169-193] The `except Exception → EmbeddingConfigError` wrappers
  around `LocalSTEmbeddings(...)`/`HFInferenceEmbeddings(...)` remain effectively unreachable
  (both constructors are lazy). A local ST model whose weights are not cached fails at
  `embed_query` and is classified transient → BM25-only, not `retrieval_unavailable`. Carried
  from round 5; consistent with the current spec (spec only names "unloadable model at init").
- [tests/rag/test_hybrid_retriever.py:2289-2476] `TestEmbeddingE2EThroughSearchSecFilings` mocks
  `HybridRetriever.retrieve` (side_effect/return_value), so it verifies the `search_sec_filings`
  error-mapping, not the real `retrieve → vector_search → get_embeddings` path. Only
  `TestHuggingfaceWithoutToken::test_hf_no_token_raises_embedding_config_error` exercises the
  real `get_embeddings`. Carried from round 5; acceptable for this gate.

## Checks run

```
$ python3 -m pytest -q -p no:cacheprovider tests/rag tests/test_schema_env_override.py
  → 303 passed, 19 skipped, 1 warning

$ PYTHONPATH=/tmp/ci_sim python3 -m pytest -q -p no:cacheprovider -p block_spark tests/rag tests/test_schema_env_override.py
  → 303 passed, 19 skipped, 1 warning   (pyspark + databricks.connect hidden)

$ python3 -m pytest -q -p no:cacheprovider 'tests/rag/test_hybrid_retriever.py::TestHuggingfaceWithoutToken' 'tests/rag/test_hybrid_retriever.py::TestEmbeddingE2EThroughSearchSecFilings'
  → 8 passed

$ # Mutation 1: delete `except EmbeddingConfigError` block in agent/tools_retrieval.py
$ python3 -m pytest -q ...::TestHuggingfaceWithoutToken::test_hf_no_token_search_sec_filings_returns_unavailable ...::TestEmbeddingE2EThroughSearchSecFilings::test_missing_token_returns_retrieval_unavailable
  → 2 failed   ✔ finding #1/#2 pin holds

$ # Mutation 2: safe_msg -> str(e) in the config handler
$ python3 -m pytest -q ...::TestEmbeddingE2EThroughSearchSecFilings::test_token_value_never_leaks_in_message
  → 1 failed (Secret token value leaked)   ✔ no-secret pin holds

$ # Live probe: retrieve() raising plain CorpusUnavailableError
$ python3 - (mocked HybridRetriever)
  → {'error':'retrieval_unavailable','message':'SEC filing corpus could not be loaded…','ticker':'NVDA'}  ✔ no reason key

$ grep -n 'HF_TOKEN.*or.*SEC filing corpus' tests/ → (no matches)   ✔ no or-clause remains

$ git status → clean (all mutations reverted)
```
===VERDICT END===
