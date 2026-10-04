# BUILD rag-eval-harness round 11 (builder: MiMo; checker: DeepSeek; reviewer: Codex)

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/rag-eval-harness. Commit after each item, descriptive messages.
NEVER delete or weaken existing tests. Codex review: .agents/codex/VERDICT-rag-eval-harness-review2.md (4 blocking).

1 (blocking). Metrics. evals/rag_eval/metrics.py:24, :41, :62 slice the raw ranking before deduplicating, so duplicate relevant ids inflate
   scores (nDCG 1.6309 for ranking ["g","g"] vs gold ["g"]); a 500-case randomized reference found 58 recall / 44 MRR / 171 nDCG mismatches.
   - Deduplicate the ranking (keep first occurrence, preserve order) BEFORE taking top-k, for recall@k, MRR, nDCG@k.
   - nDCG ideal DCG uses min(k, |gold|) distinct gold items; result must be within [0, 1].
   - Aggregation (:291): answerable rows with ZERO gold ids are excluded from the mean (and counted/reported separately), not averaged as 0.
   - Add an independent reference implementation in the TEST (not imported from production) and a seeded randomized property test
     (≥ 500 cases incl. duplicates, empty rankings, k > len(ranking)) asserting equality with production. Explicit cases: ["g","g"] vs ["g"]
     → nDCG 1.0; perfect row + zero-gold row → recall@5 1.0 with 1 excluded.
   Mutation proof (in /tmp copy, paste output): remove the dedupe → property test FAILS.
2 (blocking). Ticker-filter-off ablation is ineffective for hybrid modes: retrieve_mode() delegates hybrid_rrf / hybrid_rerank to methods that
   re-derive the ticker from the query (api/services/hybrid_retriever.py:629, :778, :790). When the harness requests ticker filter OFF
   (ticker=""), no mode may re-derive a ticker. Thread an explicit `ticker_filter: bool` (or sentinel) through; production default behaviour
   unchanged. Test: query "NVIDIA revenue", ticker filter off → all four modes (bm25, dense, hybrid_rrf, hybrid_rerank) run with no ticker
   filter (assert on the filter actually applied). Mutation: restore query-derived ticker in hybrid → FAILS.
3 (blocking). Offline + fast. Dense harness tests call the real embedding provider (tests/rag/test_rag_eval_retrieval.py:46); the guard only
   stubs the reranker (conftest.py:158). Provide a deterministic fake embedding provider fixture (hash-seeded vectors of the right dim, or the
   precomputed tests/rag/fixtures/rag_eval/embeddings_smoke.npz) used by every dense/hybrid harness test and by
   test_verify_entailment_no_model; no Hugging Face download or model load in tests/rag. Acceptance: `python3 -m pytest tests/rag -q` with the
   network guard completes with 0 timeouts; tests/rag total runtime < 120 s on this machine — report the time.
4 (blocking). Substring-fallback results from search_sec_filings omit chunk_id (agent/tools_retrieval.py:168). Every successful result must
   include chunk_id (null only if genuinely unavailable — prefer the real id). Test: force the substring fallback path → every result has a
   chunk_id key with the expected value.
Acceptance: python3 -m pytest tests/rag -q all pass, 0 timeouts; pyspark hidden (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps).
.agents/mimo/VERDICT-rag-eval-harness-round11.md with counts, runtime and mutation outputs. Commit everything.
