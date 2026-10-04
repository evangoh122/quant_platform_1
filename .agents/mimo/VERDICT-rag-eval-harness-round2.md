# VERDICT: rag-eval-harness-round2 — MiMo
**Status:** APPROVED
**Round:** 2

## Blocking findings
None.

## Non-blocking notes

### sec_analyzer.py change justification
`api/services/sec_analyzer.py` line 27: comment updated from
`# LLM client (same pattern as evals/ragas_eval.py)` to
`# LLM client (same pattern as evals/rag_eval/generation.py)`.
This is a doc-only change reflecting the file rename (`ragas_eval.py` deleted,
replaced by `evals/rag_eval/generation.py`). No behavior change. Justified and kept.

### Retrieve vs retrieve_mode equivalence
`TestRetrieveMatchesRetrieveMode` compares document *sets* (not ordering)
because the cross-encoder reranker reorders by relevance score.
Both `retrieve()` and `retrieve_mode(mode="hybrid_rerank")` reuse the same
`bm25_search`, `vector_search`, and `rrf_fuse` functions — no duplicated algorithms.

### get_embeddings() fix scope
Changed `api/services/embeddings.py:get_embeddings()` to read `config.EMBEDDING_PROVIDER`
at call time instead of using the stale module-level `EMBEDDING_PROVIDER` constant.
The module-level constants (`EMBEDDING_PROVIDER`, `ST_EMBEDDING_MODEL`, etc.) are
still exported for backward compatibility but no longer used by `get_embeddings()`.
This is a minimal, targeted fix — the `LocalSTEmbeddings` and `HFInferenceEmbeddings`
classes are unchanged.

### Golden set
CLI `--golden <path>` is required (cli.py:96). No hardcoded golden file path.
Tests use only `tests/rag/fixtures/rag_eval/golden_smoke.jsonl` (5-item fixture).

### Deleted files confirmed clean
`grep -r 'import.*run_eval\|from.*run_eval\|import.*ragas_eval\|from.*ragas_eval'`
returns zero hits across the codebase. The LLM-judge scorers (faithfulness,
answer_relevancy, context_precision, context_recall) live in `evals/rag_eval/generation.py`.

## Checks run
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase` → 635 passed, 67 skipped, 0 failures
- `python3 -m pytest -q tests/rag -p no:randomly -p no:cacheprovider` → 356 passed, 19 skipped, 0 failures
- `python3 -m pytest -q tests/rag -p no:cacheprovider` (randomly enabled) → 356 passed, 19 skipped, 0 failures
- pyspark + databricks.connect mocked, `tests/rag` → 356 passed, 19 skipped, 0 failures
- LF line endings verified on all committed files (`file` command)