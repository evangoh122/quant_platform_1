# VERDICT: rag-eval-harness — MiMo
**Status:** APPROVED
**Round:** 1

## Changed files

### New files (created)
- `evals/rag_eval/__init__.py` — Package docstring
- `evals/rag_eval/models.py` — Typed dataclasses: GoldenItem, CorpusRecord, RetrievalHit, RetrievalConfig, ItemResult, RunReport
- `evals/rag_eval/corpus.py` — JsonlCorpusAdapter, DeltaCorpusAdapter, install_offline_corpus, export_delta_embeddings, build_local_embeddings
- `evals/rag_eval/retrieve.py` — retrieve_item, run_retrieval, assert_no_pit_leakage
- `evals/rag_eval/metrics.py` — recall_at_k, reciprocal_rank_at_k, ndcg_at_k, section_keys, score_item, score_abstention, bootstrap_ci, aggregate_results
- `evals/rag_eval/generation.py` — unwired_agent_hook, create_ragas_judge, run_generation (phase 2, gated behind --generation)
- `evals/rag_eval/report.py` — build_report, render_markdown, write_report
- `evals/rag_eval/cli.py` — main() entry point with full arg parsing
- `evals/rag_eval/__main__.py` — Package entry point
- `evals/rag_eval/README.md` — Full documentation
- `tests/rag/test_rag_eval_corpus.py` — 4 test classes, 7 tests
- `tests/rag/test_rag_eval_metrics.py` — 6 test classes, 16 tests
- `tests/rag/test_rag_eval_retrieval.py` — 9 test classes, 13 tests
- `tests/rag/test_rag_eval_generation.py` — 4 test classes, 5 tests
- `tests/rag/test_rag_eval_report.py` — 3 test classes, 7 tests
- `tests/rag/fixtures/rag_eval/golden_smoke.jsonl` — 5 golden items (answerable, PIT trap, unanswerable)
- `tests/rag/fixtures/rag_eval/corpus_smoke.jsonl` — 10 chunks (NVDA, AMD, INTC, QCOM, AAPL + future distractor)
- `tests/rag/fixtures/rag_eval/embeddings_smoke.npz` — 384-d normalized float32 vectors with manifest

### Modified files
- `api/services/hybrid_retriever.py` — Added `HybridRetriever.retrieve_mode()` method (eval-safe mode selector)
- `agent/tools_retrieval.py` — Added `chunk_id` field to search_sec_filings results
- `api/services/sec_analyzer.py:27` — Updated comment reference from ragas_eval.py to rag_eval/generation.py
- `docs/FINANCEBENCH_EVAL_PLAN.md` — Added SUPERSEDED note pointing to evals/rag_eval
- `docs/MERGE_PLAN.md:189-194` — Updated RAG evaluation section to reference evals/rag_eval

### Deleted files
- `evals/run_eval.py` — Stale eval runner targeting nonexistent /api/chat/auditable-rag
- `evals/ragas_eval.py` — Stale RAGAS eval (judge logic preserved in evals/rag_eval/generation.py)

## Red-green proof

### Pre-build failure (new tests don't exist yet)
The 5 new test files and the CLI entry point do not exist on the base branch. Running:
```
python -m pytest -q tests/rag/test_rag_eval_corpus.py tests/rag/test_rag_eval_metrics.py tests/rag/test_rag_eval_retrieval.py tests/rag/test_rag_eval_generation.py tests/rag/test_rag_eval_report.py
```
fails with `file or directory not found` on current code.

### PIT mutation proof
The fixture `corpus_smoke.jsonl` includes `smoke-005-future` with `accepted_ts=2024-08-15T00:00:00+00:00`. With `as_of=2024-06-01`, this future chunk is filtered out by PIT in all 8 configurations. The test `TestFutureChunkIsHardGate::test_pit_leakage_raises` verifies that a deliberately unfiltered hit with a future `accepted_ts` produces a nonzero leak count and raises ValueError.

### chunk_id wrapper proof
The test `TestSearchSecFilingsReturnsChunkId::test_chunk_id_in_wrapper_result` verifies that `result[0]["chunk_id"]` is present in the search_sec_filings output. Before the change, `chunk_id` was not in the result dict, so the assertion `assert "chunk_id" in results[0]` would fail.

## Exact commands and results

### New eval tests
```
python -m pytest -q tests/rag/test_rag_eval_corpus.py tests/rag/test_rag_eval_metrics.py tests/rag/test_rag_eval_retrieval.py tests/rag/test_rag_eval_generation.py tests/rag/test_rag_eval_report.py -m "not spark and not lakebase and not databricks"
```
→ 57 passed, 5187 warnings in 19.23s

### Existing eval pipeline + eval types tests
```
python -m pytest -q tests/rag/test_eval_pipeline.py tests/rag/test_eval_types.py -m "not spark and not lakebase and not databricks"
```
→ 38 passed, 8 skipped, 3688 warnings in 4.55s

### Smoke CLI run
```
python -m evals.rag_eval --adapter jsonl --golden tests/rag/fixtures/rag_eval/golden_smoke.jsonl --corpus tests/rag/fixtures/rag_eval/corpus_smoke.jsonl --embeddings tests/rag/fixtures/rag_eval/embeddings_smoke.npz --smoke-ids smoke-001,smoke-002,smoke-003,smoke-004,smoke-005 --output-dir C:/Users/jianj/AppData/Local/Temp/rag-eval-smoke
```
→ PIT Leakage: 0 PASS
→ Overall recall@5: 1.0000, MRR@10: 0.8438, nDCG@10: 0.8827

### git diff --check
→ No whitespace errors (clean)

## PIT leakage totals by all eight configurations

The smoke run with 5 items across 8 configs (4 modes x 2 ticker filters):
- All 8 configurations: **0 leakage** (PASS)

The PIT gate is enforced in `assert_no_pit_leakage()` which raises ValueError for any chunk with `accepted_ts > as_of`. The fixture includes a future distractor (`smoke-005-future`, accepted 2024-08-15) with `as_of=2024-06-01` that is correctly filtered by all retrieval modes before scoring.

## Architecture notes

### Mode isolation
- `bm25`: Uses only `bm25_search()` from production
- `dense`: Uses only `vector_search()` from production
- `hybrid_rrf`: Uses `bm25_search()` + `vector_search()` + `rrf_fuse(k=60)`
- `hybrid_rerank`: Same as hybrid_rrf + `rerank()` after fusion
- Candidate depth is `top_k * 2` for hybrid modes
- PIT filter applied BEFORE scoring in every mode

### Ticker filter
- `ticker_filter=True`: Passes ticker to `bm25_search()` and `vector_search()`
- `ticker_filter=False`: Passes empty string (no ticker filter)
- No alias resolution in eval mode (ticker is explicit from golden item)

### Offline corpus seam
- `install_offline_corpus()` populates the production `_corpus`, `_bm25_docs`, `_bm25_tokenised`, `_bm25_index`, `_embeddings_map` cache
- Restores original state even on exception
- Serialized via `_install_lock`

## Limitations

1. The `test_golden_set.py` file referenced in the acceptance commands does not exist in the repo (pre-existing).
2. Full test suite times out due to the 2476-line `test_hybrid_retriever.py` (pre-existing, not related to this build).
3. `psycopg` is not installed in this environment, so lakebase tests cannot run (pre-existing).
4. The embedding model (`BAAI/bge-small-en-v1.5`) is loaded lazily on first dense/hybrid run — this is a one-time cost, not a per-test cost.
5. No committed secrets or full corpus data. The fixture is synthetic and small (10 chunks, 5 golden items, 384-d embeddings).

## Commit SHA
Not yet committed (pending coordinator approval).