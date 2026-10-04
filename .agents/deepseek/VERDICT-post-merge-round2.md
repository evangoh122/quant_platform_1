===VERDICT START===
# VERDICT: post-merge-round2 — DeepSeek (schema/API-contract lane)
**Status:** CHANGES_REQUESTED
**Round:** 2

Read-only review of commit `08fed84` ("fix: make config.py single source of truth
for embedding model/dim"). The default path (huggingface / bge-small / 384) is
now correct and single-sourced, the new test is non-vacuous, and nothing else
regressed. One blocking finding remains on the non-default
`sentence_transformers` provider: the dimension guard cannot catch a
provider↔index dimension mismatch there, so it degrades to a substring fallback
instead of a clean `retrieval_unavailable`.

## Answers to the check questions

### 1. Single source of truth?
Yes, for the runtime read path. `api.services.embeddings` now imports
`EMBEDDING_PROVIDER`, `ST_EMBEDDING_MODEL`, `EMBEDDING_DIM`,
`EMBEDDING_QUERY_PREFIX` from `api.config` (`embeddings.py:24-27`), and
`HFInferenceEmbeddings` uses `config.HF_EMBEDDING_MODEL` (`embeddings.py:177`).
`hybrid_retriever` imports `EMBEDDING_DIM` from `embeddings` (`hybrid_retriever.py:36`).
With the default provider (`huggingface`) all three agree:
`HF_EMBEDDING_MODEL == "BAAI/bge-small-en-v1.5"` and `EMBEDDING_DIM == 384`.
Verified at runtime (see "Checks run").

### 2. Other providers — `EMBEDDING_PROVIDER=sentence_transformers`
- Model: `Qwen/Qwen3-Embedding-0.6B` (`api/config.py:185`), which is **1024-d**
  (`api/config.py:208-209` returns `1024` for the ST branch).
- The stored Delta index is **384-d** bge-small (built by
  `pipelines/build_sec_embeddings.py:28-29`, and stated in the module docstrings).
- **The 384-d index does NOT produce a clean `retrieval_unavailable` here.**
  `vector_search`'s guard compares the query vector against the *configured*
  `EMBEDDING_DIM` (`hybrid_retriever.py:501`), which for ST is `1024`. A 1024-d
  query vector passes the guard (`1024 != 1024` → False), then
  `_cosine_similarity`/`np.dot` (`hybrid_retriever.py:524`, `:470-472`) raises a
  raw `ValueError` against the 384-d stored vectors. That is a blocking finding
  (see below).

### 3. Env overrides
Both work and propagate through the whole chain:
- `HF_EMBEDDING_MODEL=<x>` → `config.HF_EMBEDDING_MODEL == <x>` (and
  `get_embeddings()` reads `config.HF_EMBEDDING_MODEL` at `embeddings.py:177`).
- `EMBEDDING_DIM=768` → `config.EMBEDDING_DIM == embeddings.EMBEDDING_DIM ==
  hybrid_retriever.EMBEDDING_DIM == 768`. Unset → all revert to 384.

### 4. New test is non-vacuous (proven in /tmp)
- Mutation A: `HF_EMBEDDING_MODEL` default → `XXXX-MUTATED-MODEL` ⇒
  `test_config_hf_model_default` **fails** (1 failed).
- Mutation B: `EMBEDDING_DIM` huggingface `384` → `4096` ⇒
  `test_config_embedding_dim_hf_provider`, `test_embeddings_dim_matches_config`,
  `test_hybrid_retriever_uses_config_dim` **fail** (3 failed).

### 5. No other regression
Full requested suite passes identically with and without
`pyspark`/`databricks.connect`: **283 passed, 19 skipped** in both runs.

## Blocking findings
- [`api/services/hybrid_retriever.py:501` + `api/config.py:208-209`]
  The dimension guard validates the query vector against the *configured*
  `EMBEDDING_DIM`, not the stored index dimension. For
  `EMBEDDING_PROVIDER=sentence_transformers` this commit set
  `ST_EMBEDDING_MODEL="Qwen/Qwen3-Embedding-0.6B"` / `EMBEDDING_DIM=1024`
  (previously `embeddings.py` defaulted the ST backend to
  `BAAI/bge-small-en-v1.5` / 384). → Concrete failure: an operator keeps the
  shipped 384-d bge-small index but switches provider to `sentence_transformers`.
  The 1024-d query vector passes the guard (`1024 != 1024` is False), then
  `np.dot(1024, 384)` raises `ValueError` at `hybrid_retriever.py:524`.
  `agent/tools_retrieval.py:128-171` catches it as a generic `Exception` and
  silently falls back to the substring filter (`retrieval_mode:
  "substring_fallback"`) — the exact "wrong-dim query silently degrades" failure
  that Fix #3 (CodeRabbit) was meant to surface as a clean `retrieval_unavailable`.
  The guard should compare `len(qvec)` against the stored index dimension
  (e.g. the first entry in `_embeddings_map`), or the ST default should be
  aligned to the 384-d index.

## Non-blocking notes
- `pipelines/build_sec_embeddings.py:28-29` still reads
  `ST_EMBEDDING_MODEL`/`EMBEDDING_DIM` from env directly, not from `api.config`.
  It defaults to bge-small/384 (consistent with the shipped index) but is a
  second source of truth for the index builder that this commit did not unify.
- Stale docstrings now that the ST default changed:
  `api/services/embeddings.py:5` ("in-process ST model (BAAI/bge-small-en-v1.5,
  384-d)") and `:38` ("BAAI/bge-small-en-v1.5 produces 384-d") no longer match
  `ST_EMBEDDING_MODEL="Qwen/Qwen3-Embedding-0.6B"`.
- `tests/rag/test_embedding_config.py` has no trailing newline (cosmetic).

## Checks run
```
$ python3 -m pytest -q -p no:cacheprovider tests/rag tests/test_schema_env_override.py
                                                                  → 283 passed, 19 skipped
$ # pyspark + databricks.connect hidden via sys.meta_path ImportError blocker
$ python3 -c '…block pyspark, databricks.connect…; pytest.main([…tests/rag tests/test_schema_env_override.py])'
                                                                  → 283 passed, 19 skipped
$ # /tmp mutation A (HF_EMBEDDING_MODEL default)                 → 1 failed
$ # /tmp mutation B (EMBEDDING_DIM 384→4096)                      → 3 failed
$ # env-override probe: HF_EMBEDDING_MODEL, EMBEDDING_DIM=768     → config=embeddings=hybrid=768
$ # ST-provider probe: EMBEDDING_PROVIDER=sentence_transformers   → Qwen3-0.6B / 1024-d,
$ #   guard 1024!=1024 → False; np.dot(1024,384) → ValueError
```
===VERDICT END===
