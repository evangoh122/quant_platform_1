===VERDICT START===
# VERDICT: post-merge-coderabbit — DeepSeek (schema/API-contract lane)
**Status:** APPROVED
**Round:** 1

Read-only review of `fix/post-merge-coderabbit` vs `origin/main` (`.agents/` excluded).
All five check areas verified against the code and by running the tests. No
blocking findings.

## Answers to the check questions

### 1. RAG ticker filter (`api/services/hybrid_retriever.py::bm25_search`)
- **PIT filter still before scoring.** `bm25_search` runs `_pit_filter(_bm25_docs, as_of)`
  at `hybrid_retriever.py:442`, *then* the ticker filter at `:449-452`, *then* rebuilds a
  temp `BM25Okapi` and scores. Order is correct.
- **Explicit ticker → hard filter (correct).** `search_sec_filings` always passes
  `ticker=symbol` (an explicit, normalized symbol), so `resolve_ticker_from_query` returns it
  unchanged and both `bm25_search` and `vector_search` hard-filter to it. The original leak
  (BM25 boost kept non-matching chunks through RRF) is closed; this now matches
  `vector_search`'s pre-existing hard filter.
- **Mutation proof.** In `/tmp/qp1-mut` I removed the hard-filter block; the new tests fail:
  `TestBM25TickerFilter` → **3 failed** (`test_bm25_filters_by_ticker_not_just_boosts`,
  `test_bm25_returns_empty_when_no_ticker_match`, `test_hybrid_no_leak_across_tickers`).
  The test `test_hybrid_no_leak_across_tickers` reproduces the leak exactly
  (`assert 'AAPL' not in ['NVDA','NVDA','AAPL']`).

### 2. Corpus load retry (`_load_corpus`)
- Both `except CorpusUnavailableError` (`:342-350`) and `except Exception` (`:351-360`) now
  reset `_corpus_loaded=False` and clear `_corpus`, `_embeddings_map`, `_bm25_docs`,
  `_bm25_tokenised`, `_bm25_index`, then re-raise `CorpusUnavailableError`. Next call retries
  from scratch.
- No *transient-failure* path leaves `_corpus_loaded=True` with an empty corpus.
- Error surfaced as `CorpusUnavailableError` → `search_sec_filings` (`agent/tools_retrieval.py:120-127`)
  returns `{"error":"retrieval_unavailable", ...}`, not the substring fallback. Confirmed.

### 3. Embedding dimension guard + HF default
- HF default changed to `BAAI/bge-small-en-v1.5` (`embeddings.py:175`), matching the module
  `EMBEDDING_DIM=384` default (`embeddings.py:24`).
- `vector_search` raises `CorpusUnavailableError` on `len(qvec) != EMBEDDING_DIM`
  (`hybrid_retriever.py:500-505`) → surfaces as `retrieval_unavailable`. No silent fallback.
- Test `test_dim_mismatch_raises_corpus_unavailable` passes; `test_correct_dim_works` passes.

### 4. `build_sec_embeddings` read-error propagation
- Blind `except Exception → existing_ids = set()` removed. The `spark.table(EMBEDDINGS_TABLE)`
  read error now propagates before any write (`build_sec_embeddings.py:72-75`).
- `TestBuildEmbeddingsReadError.test_read_error_propagates` asserts the raise and
  `createDataFrame.assert_not_called()`. Passes.

### 5. CI/CD
- **SHAs vs tags** (`git ls-remote`): all 5 match.
  - `actions/checkout@11d5960…` == `refs/tags/v4` ✓
  - `actions/setup-node@49933ea…` == `refs/tags/v4` ✓
  - `actions/setup-python@a26af69…` == `refs/tags/v5` ✓
  - `databricks/setup-cli@095d26a…` == `refs/tags/v0.276.0` ✓
  - `gitleaks/gitleaks-action@ff98106…` == peeled `refs/tags/v2^{}` ✓ (the `v2` tag object
    is `dcedce43…`, which dereferences to the pinned commit).
- **persist-credentials: false** on every checkout (ci.yml ×4, cd.yml ×1).
  `coderabbit-trigger.yml` has no checkout step by design (comment-only job).
- **bundle-validate auth gate**: validation steps gated on
  `HOST != '' && (CLIENT_ID != '' || TOKEN != '')`. Skips cleanly when unset.
- **start_app** `workflow_dispatch` boolean, default `false`; when true runs
  `databricks bundle run quant_platform -t <target>` (the app resource key only). No job
  (`silver_gold_refresh`, `ml_ablation`) or pipeline is run from CD.
- **Schema plumbing**: app `config.env` sets `SCHEMA: ${var.schema}` → read by
  `api/config.py::Config.SCHEMA` (env) and by `hybrid_retriever.py` / `db/delta_adapter.py`
  (env). Job `--schema ${var.schema}` → `run_silver_gold.py::main` rebinds module `SCHEMA` and
  `FQN` (`:305-308`), which all downstream `FQN` uses see. `tests/test_schema_env_override.py`
  (5 tests) covers default + override + FQN rebind.
- **Module-state leak**: `test_schema_env_override` reloads `settings`/`api.config` per test and
  monkeypatches `r.SCHEMA`/`r.FQN` before `main()` rebinds them, so globals are restored.
  `fake_pyspark` is function-scoped (`monkeypatch.setitem`).

## Non-blocking notes
- `hybrid_retriever.py:431-434` docstring is stale: it still claims BM25 "multiplied by
  `ticker_boost`", but the boost branch was removed. `ticker_boost` is now an unused parameter
  in `bm25_search` (still threaded to `rrf_fuse` via `retrieve`, where it is still used).
- Divergence from `BUILD-rag-coderabbit.md` item #1 ("keep the boost path only for ticker
  unset / resolved-from-query"): a resolved-from-query ticker now *hard-filters*, not boosts.
  Not observed in the agent flow (`search_sec_filings` always passes an explicit symbol), and it
  matches `vector_search`'s pre-existing hard filter, but a direct
  `HybridRetriever.retrieve("compare nvidia and intel")` resolves `NVDA` and drops `INTC`.
- `_load_corpus` on a genuinely-empty corpus (0 chunk rows) sets `_corpus_loaded=True` with an
  empty `_corpus` and returns `False`; the *next* call raises `CorpusUnavailableError("…empty
  after previous load failure")`. Outcome (`retrieval_unavailable`) is correct but the message
  is misleading for a truly empty table (it is not a "previous load failure").
- `api/config.py` embedding defaults are stale relative to `api/services/embeddings.py`:
  `HF_EMBEDDING_MODEL` still `"Qwen/Qwen3-Embedding-8B"` (`api/config.py:178`) and
  `EMBEDDING_DIM` still `4096` for the huggingface provider (`:210-211`), while the actual HF
  default is now bge-small (384-d). Telemetry (`ACTIVE_EMBEDDING_MODEL`, `EMBEDDING_DIM`)
  would misreport; the retrieval path itself is unaffected.
- `bundle-validate` gate checks `CLIENT_ID || TOKEN` but not `CLIENT_SECRET`; a repo that sets
  `CLIENT_ID` without `CLIENT_SECRET` (and no token) will *run* validation and fail rather than
  skip. Matches the BUILD spec letter ("client id with OIDC") but M2M OAuth also needs the secret.

## Checks run
```
$ git diff origin/main -- . ':(exclude).agents/'          → reviewed (20 files)
$ python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase
                                                           → 551 passed, 67 skipped
$ PYTHONPATH=/tmp/nopyspark python3 -m pytest -q -p no:cacheprovider tests/rag
                                                           → 272 passed, 19 skipped
$ # mutation (remove BM25 ticker hard filter, /tmp/qp1-mut)
$ PYTHONPATH=/tmp/nopyspark python3 -m pytest -q tests/rag/test_hybrid_retriever.py::TestBM25TickerFilter
                                                           → 3 failed
$ python3 -m pytest -q -p no:cacheprovider tests/test_schema_env_override.py
                                                           → 5 passed
$ python3 /tmp/yamlcheck.py (yaml.safe_load .github/workflows/*.yml)
                                                           → OK (cd.yml, ci.yml, coderabbit-trigger.yml)
$ git ls-remote <action repos> refs/tags/<tag>             → all SHAs match (gitleaks v2 peeled)
$ grep secret-scan of diff                                 → none found
```
===VERDICT END===
