# VERDICT: rag-coderabbit — MiMo
**Status:** APPROVED
**Round:** 1

## Summary

Fixed all 4 CodeRabbit findings from PR #18. Each fix has a regression test that fails on the pre-fix code and passes after.

## Fixes applied

1. **[Major] BM25 ticker filter** (`hybrid_retriever.py:430-434`): When `ticker` is set, filter BM25 candidates to that ticker before ranking. Previously only boosted matching docs, allowing other companies' chunks to leak through RRF fusion.

2. **[Major] Transient load failure retry** (`hybrid_retriever.py:348-360`): On exception, clear partial `_corpus`, `_embeddings_map`, and `_bm25_*` state; leave `_corpus_loaded = False`; re-raise. Previously set `_corpus_loaded = True`, permanently disabling retrieval.

3. **[Major] Embedding dim check** (`hybrid_retriever.py:497-501`, `embeddings.py:175`): Changed HF default model from `Qwen/Qwen3-Embedding-8B` (4096-d) to `BAAI/bge-small-en-v1.5` (384-d). Added dimension check in `vector_search` that raises `CorpusUnavailableError` on mismatch.

4. **[Minor] Don't swallow read errors** (`build_sec_embeddings.py:72-76`): Removed blind `except Exception` that set `existing_ids = set()`. Read errors now propagate.

## Regression tests (7 new, all fail on pre-fix code)

| Test class | Test | Pre-fix failure |
|:--|:--|:--|
| `TestBM25TickerFilter` | `test_bm25_filters_by_ticker_not_just_boosts` | AAPL leaked through when ticker=NVDA |
| `TestBM25TickerFilter` | `test_bm25_returns_empty_when_no_ticker_match` | Returned all docs when ticker=MSFT |
| `TestBM25TickerFilter` | `test_hybrid_no_leak_across_tickers` | AAPL in hybrid results with ticker=NVDA |
| `TestTransientLoadFailureRetry` | `test_first_load_fails_second_succeeds` | `_corpus_loaded` stayed True after failure |
| `TestTransientLoadFailureRetry` | `test_partial_state_cleared_on_failure` | Partial `_corpus` not cleared |
| `TestEmbeddingDimCheck` | `test_dim_mismatch_raises_corpus_unavailable` | `ValueError` from numpy dot instead of clean error |
| `TestBuildEmbeddingsReadError` | `test_read_error_propagates` | `build()` silently succeeded |

## Checks run

- `python3 -m pytest -q tests/rag` → **272 passed, 19 skipped** (6.09s)
- `PYTHONPATH=/tmp/nopyspark python3 -m pytest -q tests/rag` → **272 passed, 19 skipped** (5.54s)
- Pre-fix regression: `pytest -k 'TestBM25TickerFilter or TestTransientLoadFailureRetry or TestEmbeddingDimCheck or TestBuildEmbeddingsReadError'` on reverted code → **7 failed, 1 passed** (0.68s)

## Files changed

- `api/services/hybrid_retriever.py` — fixes #1, #2, #3
- `api/services/embeddings.py` — fix #3
- `pipelines/build_sec_embeddings.py` — fix #4
- `tests/rag/test_hybrid_retriever.py` — regression tests