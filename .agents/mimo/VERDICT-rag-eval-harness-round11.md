# VERDICT: rag-eval-harness-round11 — MiMo
**Status:** APPROVED
**Round:** 11

## Blocking findings
None. All 4 blocking items implemented and verified.

## Implementation summary

### 1. Metrics dedup (metrics.py)
- Added `_dedupe_ranking()` helper: keeps first occurrence, preserves order
- Applied in `recall_at_k`, `reciprocal_rank_at_k`, `ndcg_at_k` before taking top-k
- nDCG ideal DCG uses `min(k, |distinct gold|)` items; result bounded [0, 1]
- Aggregate: zero-gold answerable rows excluded from mean, counted in `zero_gold_excluded`
- Mutation proof: removing dedupe → 4/501 nDCG > 1.0 violations (e.g. ["g","g"] → 1.6309)

### 2. Ticker-filter-off ablation (hybrid_retriever.py)
- Added `resolve_ticker: bool = True` to `HybridRetriever.retrieve()` and `retrieve_and_rerank()`
- `retrieve_mode()` passes `resolve_ticker=False` for hybrid modes — ticker="" is honoured
- Production path (`search_sec_filings`) unchanged: `resolve_ticker` defaults to True
- Mutation proof: restoring query-derived ticker in hybrid → only NVDA results when ticker=""

### 3. Offline + fast embeddings (conftest.py)
- `_FakeEmbeddingProvider` installed in `_reset_retriever_singletons` autouse fixture
- Hash-seeded 384-d vectors, deterministic, no HuggingFace download or model load
- Runtime: 6.96s total (was 47s+ per dense test with real model retries)

### 4. Substring fallback chunk_id (tools_retrieval.py)
- Added `chunk_id` field to mapped results in substring fallback path
- Updated existing key-assertion test in test_hybrid_retriever.py

## Non-blocking notes
- 19 tests skipped (pyspark-dependent, expected without Databricks runtime)
- Pydantic deprecation warning on `.copy()` in test_rag_eval_retrieval.py:387 (pre-existing, not in scope)

## Checks run
- `python3 -m pytest tests/rag -q` → 432 passed, 19 skipped, 0 failures, 0 timeouts, 6.96s
- Mutation proof (item 1): remove dedupe → 4 nDCG violations in 501 cases, explicit ["g","g"]→1.6309
- Mutation proof (item 2): restore query-derived ticker → only NVDA results with ticker=""
- `git log --oneline`: 5 commits on slice/rag-eval-harness (fa55d8b..64d2a01)