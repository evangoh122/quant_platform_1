===VERDICT START===
# VERDICT: post-merge-round3 — DeepSeek (schema/API-contract lane)
**Status:** APPROVED
**Round:** 3

Read-only re-check of commit `792e746` ("fix(retriever): validate query dim against
stored index, not configured EMBEDDING_DIM"). My round-2 blocking finding is
resolved: the dimension guard now compares the query vector against the **stored**
index dimension (recorded at corpus load) rather than the configured
`EMBEDDING_DIM`, and the sentence-transformers default is restored to
`BAAI/bge-small-en-v1.5` (384-d). The previously failing scenario —
`EMBEDDING_PROVIDER=sentence_transformers` with a 1024-d model against the 384-d
index — now surfaces a clean `retrieval_unavailable` instead of silently degrading
to `substring_fallback`.

## Answers to the check questions

### 1. Single source of truth?
Yes, and now tighter than round 2. `api/services/embeddings.py:24-27` imports
`EMBEDDING_PROVIDER`, `ST_EMBEDDING_MODEL`, `EMBEDDING_DIM`,
`EMBEDDING_QUERY_PREFIX` from `api.config`; `HFInferenceEmbeddings` reads
`config.HF_EMBEDDING_MODEL` (`embeddings.py:177`). `hybrid_retriever` no longer
imports `EMBEDDING_DIM` at all (`792e746` removed it) — it validates against the
stored index dim (`_stored_index_dim`, `hybrid_retriever.py:225,307`) plus the
stored model name (`_stored_embedding_model`, `:226,315`). Defaults all agree:
`HF_EMBEDDING_MODEL == ST_EMBEDDING_MODEL == "BAAI/bge-small-en-v1.5"`,
`EMBEDDING_DIM == 384` (verified at runtime).

### 2. Other providers — `EMBEDDING_PROVIDER=sentence_transformers`
- Model/dim: `BAAI/bge-small-en-v1.5` / **384-d** (`config.py:184`, `:205-211`),
  matching the shipped 384-d bge-small index. `ACTIVE_EMBEDDING_MODEL` also
  returns `BAAI/bge-small-en-v1.5`.
- 1024-d model against 384-d index → `retrieval_unavailable`, **not**
  `substring_fallback`. `vector_search` raises `CorpusUnavailableError`
  ("dimension mismatch", `hybrid_retriever.py:536-540`), which
  `search_sec_filings` catches as `CorpusUnavailableError`
  (`agent/tools_retrieval.py:120-127`) and returns the structured
  `retrieval_unavailable` dict. Verified end-to-end (see "Checks run").
- Mixed stored dimensions → `CorpusUnavailableError` at load time
  (`hybrid_retriever.py:302-306`), before any scoring. Mixed stored model names →
  `CorpusUnavailableError` at load time (`:310-314`). Active-model mismatch →
  `CorpusUnavailableError` at query time (`:543-554`).

### 3. Env overrides
`HF_EMBEDDING_MODEL` and `EMBEDDING_DIM` both propagate through the full chain.
`HF_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2` +
`EMBEDDING_DIM=768` → `config.HF_EMBEDDING_MODEL`/`config.EMBEDDING_DIM` and
`embeddings.EMBEDDING_DIM` all reflect the override; unset → all revert to
bge-small / 384 (verified at runtime).

### 4. Tests are non-vacuous (proven in /tmp)
- Mutation A (HF model default) → `test_config_hf_model_default` fails (1 failed).
- Mutation B (EMBEDDING_DIM 384→4096) → 3 fail.
- Mutation C (remove the stored-index-dim guard) →
  `test_1024d_query_against_384d_index_returns_unavailable` fails with
  `ValueError: shapes (1024,) and (384,) not aligned` — proving the guard is
  exactly what prevents the raw `np.dot` crash my round-2 finding described.

### 5. Nothing else regressed
Requested suite passes identically with and without `pyspark` +
`databricks.connect` hidden: **286 passed, 19 skipped** in both runs.
`git diff --check` on both commits is clean.

## Blocking findings
None.

## Non-blocking notes
- `hybrid_retriever.py:545` reads `os.getenv("EMBEDDING_PROVIDER", ...)` directly
  rather than `_cfg.EMBEDDING_PROVIDER`. Functionally identical (same env var,
  same `.lower()`), but a slight source-of-truth drift.
- `hybrid_retriever.py:283` now selects `embedding_model` from
  `gold_sec_chunk_embeddings`. Any pre-existing index that lacks this column would
  fail `_load_corpus`. `pipelines/build_sec_embeddings.py` writes it
  (`embedding_model = BAAI/bge-small-en-v1.5`), so shipped data is consistent —
  but this is a load-time hard dependency worth flagging for data/DDL owners.
- `pipelines/build_sec_embeddings.py` still reads `ST_EMBEDDING_MODEL`/
  `EMBEDDING_DIM` from env directly rather than `api.config` (carried over from
  round-2 non-blocking note) — a second source of truth for the index builder.

## Checks run
```
$ python3 -m pytest -q -p no:cacheprovider tests/rag tests/test_schema_env_override.py
                                        → 286 passed, 19 skipped
$ # pyspark + databricks.connect hidden via sys.meta_path ImportError blocker
$ python3 /tmp/run_hidden.py            → 286 passed, 19 skipped
$ # targeted: TestStoredIndexDimensionGuard + test_embedding_config.py → 9 passed
$ # live probe: ST 1024-d vs 384-d index → CorpusUnavailableError("dimension mismatch")
$ # live probe: search_sec_filings → {"error":"retrieval_unavailable", ...} (not substring_fallback)
$ # live probe: model mismatch → CorpusUnavailableError("model mismatch")
$ # /tmp mutation A (HF model default)  → 1 failed
$ # /tmp mutation B (EMBEDDING_DIM 4096) → 3 failed
$ # /tmp mutation C (guard removed)      → 1 failed (ValueError shapes (1024,) and (384,) not aligned)
$ git diff --check 08fed84 792e746      → clean
```
===VERDICT END===
