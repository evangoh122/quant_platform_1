# BUILD: SEC RAG retrieval evaluation harness

## Goal and architectural rule

Replace the stale `evals/run_eval.py` evaluation path with `evals/rag_eval/`, exercising the production retrieval implementation behind `agent/tools_retrieval.py::search_sec_filings(symbol, query, as_of, top_k)`. Retrieval metrics are deterministic and make no LLM calls. Generation judging is phase 2 behind an explicit flag and is never enabled in CI.

MiMo runs on Windows without Databricks. The offline path must load `evals/data/sec_corpus.jsonl` and a configurable 384-dimensional embedding sidecar from the worktree; it must not import pyspark or create a Spark session. The live adapter may load Delta. The exported JSONL has chunk metadata/text but no embedding vector, so fail clearly when a dense mode is requested without a sidecar; never silently relabel BM25 as hybrid. Provide a documented one-time live export command or local bge-small build command for the sidecar, but do not commit the full corpus or full embeddings.

## Numbered changes

1. Add `evals/rag_eval/__init__.py` and `evals/rag_eval/models.py` (new files). Define typed dataclasses or frozen models `GoldenItem`, `CorpusRecord`, `RetrievalHit`, `RetrievalConfig`, `ItemResult`, and `RunReport`. Canonical retrieval modes are `bm25`, `dense`, `hybrid_rrf`, and `hybrid_rerank`; ticker filtering is an independent boolean, yielding eight ablations. `RetrievalHit` must retain `chunk_id`, ticker, accession, section, form, accepted UTC timestamp, text, rank, and available component/rerank scores.

2. Add `evals/rag_eval/corpus.py` (new file) with an adapter protocol `CorpusAdapter` and exact implementations/functions:
   - `JsonlCorpusAdapter.from_files(corpus_path: Path, embeddings_path: Path | None)`, `records()`, and `embedding_map()`. Accept a documented `.npz` sidecar keyed by chunk ID plus manifest fields `embedding_model`, `dimension=384`, `normalized`, and corpus SHA-256. Validate one-to-one IDs/dimensions, finite float32 values, model identity, normalization, and corpus hash. BM25 may run without the sidecar; dense modes must fail fast.
   - `DeltaCorpusAdapter.load()` reuses the production Delta sources `silver_sec_sections` and `gold_sec_chunk_embeddings`, preserving `accepted_epoch`. Keep all Databricks imports inside this live-only method.
   - `install_offline_corpus(adapter) -> ContextManager[None]` populates and restores the exact cache representation expected by `api.services.hybrid_retriever` (`_corpus`, `_bm25_docs`, `_bm25_tokenised`, `_bm25_index`, `_embeddings_map`, stored model/dimension, loaded flag). This is an explicit test/eval seam around production scoring, not a forked retriever implementation; restore prior globals even after errors and serialize concurrent use.
   - `export_delta_embeddings(output_path: Path)` or an equivalent CLI subcommand writes the validated sidecar for manual offline runs. Also permit deterministic local construction with the configured bge-small model, recording exact model/revision and corpus hash. Never download in CI.

3. Modify `api/services/hybrid_retriever.py:451-583` and `:588-680` only as needed to expose an evaluation-safe mode selector without duplicating algorithms. Add exact method `HybridRetriever.retrieve_mode(query, *, mode: str, ticker: str = "", as_of: datetime | None = None, top_k: int | None = None, rerank: bool = False) -> list[Document]` (or an equivalently small public seam used by both `retrieve` and the harness). It must use existing `bm25_search`, `vector_search`, `rrf_fuse(k=60)`, and `api.services.reranker.rerank`; hybrid component candidate depth is exactly `effective_top_k * 2`, reranking happens after fusion over those candidates, and PIT/ticker eligibility occurs before every scoring operation. Preserve existing `HybridRetriever.retrieve()` behavior and error semantics. Do not reimplement BM25, cosine scoring, RRF, or reranking inside `evals/`.

4. Modify `agent/tools_retrieval.py:67-121` so every successful `search_sec_filings` result includes `chunk_id`. Preserve the existing signature and existing keys. Ensure its production default is the `hybrid_rerank` path when a non-empty query has multiple hits. Add a private injectable retriever/adapter seam only if tests require it; callers must still exercise the public function. The harness must run one parity check per item/configuration where applicable against this wrapper, not merely call a lookalike.

5. Add `evals/rag_eval/retrieve.py` (new file) with exact functions `retrieve_item(item: GoldenItem, config: RetrievalConfig, adapter: CorpusAdapter) -> list[RetrievalHit]`, `run_retrieval(items, configs, adapter) -> list[ItemResult]`, and `assert_no_pit_leakage(hits, as_of) -> None`. Parse all `as_of` values as aware UTC. For ticker-filter off, pass an empty ticker and prevent query alias resolution from silently restoring the filter (the mode seam needs an explicit resolver toggle if necessary). Reject error dictionaries from `search_sec_filings` as run errors, not empty retrieval.

6. Add `evals/rag_eval/metrics.py` (new file). Implement exact pure functions `recall_at_k(ranked_ids, gold_ids, k)`, `reciprocal_rank_at_k(ranked_ids, gold_ids, k=10)`, `ndcg_at_k(ranked_ids, gold_ids, k=10)`, `section_keys(hits)`, `score_item(item, hits)`, `score_abstention(item, hits)`, `bootstrap_ci(values, *, seed=1729, samples=10_000, confidence=0.95)`, and `aggregate_results(results)`.
   - Primary exact metrics: recall@1/5/10, MRR@10, and binary-relevance nDCG@10 against `gold_chunk_ids`. Deduplicate IDs before scoring and define the zero-gold behavior explicitly as excluded from ordinary recall/MRR/nDCG aggregation.
   - Secondary metrics use unique `(accession, section)` keys derived from gold chunks/corpus, with the same recall/MRR/nDCG definitions.
   - Leakage count is the number of returned chunks with `accepted_ts > as_of`, per item and per mode/filter configuration. Missing/unparseable acceptance is an error. Sum must be exactly zero and any nonzero value raises/fails the run before report success.
   - For `unanswerable` and `point_in_time_trap`, report retrieval-level abstention/trap outcomes separately. `allowed_top_hit=true` iff top-1 is temporally allowed and, for older-answer traps, belongs to the allowed older gold evidence. For abstain traps, future evidence is forbidden and no future-answering filing may appear; for true unanswerable, label the heuristic honestly (`no_gold_retrieved`/`top_hit_present`) rather than claiming generation abstained. Do not fold these rows into ordinary answerable recall.
   - Bootstrap item-level recall@5 and reciprocal-rank values with fixed seed; report percentile 95% CIs overall, per type, and per ticker when sample size permits, plus `n` and a warning for tiny strata.

7. Add `evals/rag_eval/generation.py` (new file) for optional phase 2. Define `AgentHook = Callable[[GoldenItem, list[RetrievalHit]], AgentResponse]`, `run_generation(items, retrieval_results, agent_hook, judge)`, and a default `unwired_agent_hook(...)` that raises `NotImplementedError` with setup instructions. Adapt the existing `evals/ragas_eval.py` judge logic into functions accepting `(question, answer, contexts, gold_answer)` for faithfulness, answer relevancy, context precision, and context recall. Gate all calls behind CLI `--generation`; additionally require `--allow-paid-calls` (or a local judge configuration) before any remote request. Record provider/model, prompt version, failures, and cost metadata when available. Tests inject fake hooks/judges; CI cannot access network or secrets.

8. Add `evals/rag_eval/report.py` (new file) with `build_report(run_report) -> dict`, `render_markdown(report) -> str`, and `write_report(report, output_dir: Path, run_date: date) -> tuple[Path, Path]`. Write `evals/results/rag_eval_<date>.json` and `.md`; avoid overwrite by adding an explicit run ID suffix when the date's files exist. Include git SHA, corpus and golden SHA-256, embedding model/revision/dimension, reranker model/revision or disabled reason, RRF k=60, candidate depth, top-k values, seed, adapter, CLI args, timestamp, environment, per-item rows, eight-ablation matrix, overall/per-type/per-ticker metrics, secondary metrics, bootstrap CIs, abstention/trap results, and PIT leakage hard-gate status.

9. Add `evals/rag_eval/cli.py` and `evals/rag_eval/__main__.py` (new files). Exact entry function `main(argv: Sequence[str] | None = None) -> int`. Support `--golden`, `--corpus`, `--embeddings`, `--adapter jsonl|delta`, `--mode` (repeatable/all), `--ticker-filter on|off|both`, `--top-k` (default 10), `--seed`, `--output-dir`, `--generation`, `--allow-paid-calls`, and `--smoke-ids`. Validate the golden set before running. Default invocation performs all retrieval ablations, no generation, and exits nonzero for any PIT leak, missing required embedding artifact, wrapper parity failure, or malformed result.

10. Add pinned CI fixtures `tests/rag/fixtures/rag_eval/` (new files): five golden items spanning answerable, PIT older-answer, PIT abstain, and unanswerable behavior; a tiny JSONL corpus containing allowed and future distractors; normalized 384-d cached vectors plus manifest. The fixture is synthetic or excerpted with provenance and small enough to commit. No model loading/download, network, Spark, Databricks, or paid call is allowed.

11. Add tests:
   - `tests/rag/test_rag_eval_corpus.py`: `test_jsonl_adapter_validates_manifest`, `test_dense_requires_embeddings`, `test_offline_install_restores_production_cache`, `test_delta_import_is_lazy`.
   - `tests/rag/test_rag_eval_metrics.py`: `test_exact_chunk_metrics`, `test_secondary_accession_section_metrics`, `test_zero_gold_excluded`, `test_bootstrap_is_deterministic`, `test_abstention_and_trap_scoring`.
   - `tests/rag/test_rag_eval_retrieval.py`: `test_all_eight_ablations_run_real_production_scoring`, `test_hybrid_uses_double_candidate_depth`, `test_reranker_runs_after_rrf`, `test_ticker_filter_on_and_off_differ`, `test_search_sec_filings_returns_chunk_id`, `test_wrapper_matches_hybrid_rerank`, `test_every_mode_filters_before_scoring`, `test_future_chunk_is_hard_gate_even_if_highest_score`, `test_smoke_five_items_offline_no_network`.
   - `tests/rag/test_rag_eval_generation.py`: `test_generation_default_is_disabled`, `test_unwired_hook_fails_clearly`, `test_paid_calls_need_explicit_opt_in`, `test_fake_generation_metrics_accept_question_answer_contexts`.
   - `tests/rag/test_rag_eval_report.py`: `test_report_has_breakdowns_cis_and_config`, `test_report_refuses_success_with_pit_leak`, `test_report_writes_json_and_markdown` (write only to pytest tmp paths).

12. Retire stale code deliberately:
   - Delete `evals/run_eval.py`. It targets `golden_set.csv` and the nonexistent/stale `/api/chat/auditable-rag` route, and its answer/XBRL scoring is not this app's retrieval evaluation.
   - Delete `evals/ragas_eval.py` after moving its reusable judge prompts/parsing into `evals/rag_eval/generation.py`; remove its stale CSV and `/api/chat/auditable-rag` client path. Do not retain a compatibility wrapper that suggests the old endpoint still works.
   - Update `docs/FINANCEBENCH_EVAL_PLAN.md` to a clearly marked historical/superseded note pointing to `evals/golden/README.md` and `python -m evals.rag_eval`; correct the claim that FinanceBench overlaps this 2024-2026 corpus.
   - Update `docs/MERGE_PLAN.md:192-193` and any remaining executable/documentation references to the deleted scripts or `/api/chat/auditable-rag`. The unrelated comment in `api/services/sec_analyzer.py` should refer to `evals/rag_eval/generation.py` instead.
   - Add `evals/rag_eval/README.md` documenting offline/live commands, embedding sidecar creation, mode definitions, metric formulas, PIT gate, no-paid-CI policy, and current absence of an agent hook.

## Tests that must fail before this build

First save the pre-build failure proof in MiMo's verdict:

```bash
python -m pytest -q tests/rag/test_rag_eval_corpus.py tests/rag/test_rag_eval_metrics.py tests/rag/test_rag_eval_retrieval.py tests/rag/test_rag_eval_generation.py tests/rag/test_rag_eval_report.py -m "not spark and not lakebase and not databricks"
python -m evals.rag_eval --adapter jsonl --smoke-ids rag-v1-001,rag-v1-002,rag-v1-003,rag-v1-004,rag-v1-005
```

These must fail on current code because the package/tests do not exist. Add focused red-green proof for the existing wrapper: before editing `agent/tools_retrieval.py`, a mocked production `Document` result assertion for `result[0]["chunk_id"]` must fail. For PIT mutation proof, copy the tiny fixture to a pytest temp directory and give a future distractor the highest lexical/vector score; a deliberately unfiltered test seam must produce a nonzero leak and the hard gate must fail. Never mutate production files or committed fixtures in place.

## Acceptance commands

Run from repository root. Keep pyspark hidden and generation disabled:

```bash
python -m pytest -q tests/rag/test_rag_eval_corpus.py tests/rag/test_rag_eval_metrics.py tests/rag/test_rag_eval_retrieval.py tests/rag/test_rag_eval_generation.py tests/rag/test_rag_eval_report.py -m "not spark and not lakebase and not databricks"
python -m pytest -q tests/rag/test_golden_set.py tests/rag/test_eval_pipeline.py tests/rag/test_eval_types.py -m "not spark and not lakebase and not databricks"
python -m evals.rag_eval --adapter jsonl --golden tests/rag/fixtures/rag_eval/golden_smoke.jsonl --corpus tests/rag/fixtures/rag_eval/corpus_smoke.jsonl --embeddings tests/rag/fixtures/rag_eval/embeddings_smoke.npz --smoke-ids smoke-001,smoke-002,smoke-003,smoke-004,smoke-005 --output-dir /tmp/rag-eval-smoke
python -m pytest -q -m "not spark and not lakebase and not databricks"
git diff --check
```

Manual full run (not CI; requires local ignored corpus and embeddings):

```bash
python -m evals.rag_eval --adapter jsonl --golden evals/golden/golden_v1.jsonl --corpus evals/data/sec_corpus.jsonl --embeddings evals/data/sec_embeddings_bge_small.npz --mode all --ticker-filter both
```

Acceptance requires PIT leakage total `0` for every item and every one of the eight configurations. There is no initial quality threshold for recall/MRR; this build establishes a reproducible baseline. Any model download needed for a manual full run must be explicit and documented, never performed during tests.

## DeepSeek must check

- Confirm the offline adapter invokes production `bm25_search`, `vector_search`, `rrf_fuse`, and `rerank`; reject any shadow retrieval implementation in `evals/`.
- Verify mode isolation, RRF `k=60`, `top_k * 2` component candidates, reranking order, and on/off ticker behavior (including alias-resolution bypass).
- Trace `accepted_epoch/as_of` through JSONL loading, production cache metadata, every ablation, wrapper serialization, metrics, and reports. Run the future-distractor mutation; zero leakage is a hard gate.
- Independently calculate hand-worked recall@1/5/10, MRR@10, nDCG@10, secondary accession+section metrics, trap outcomes, and at least one bootstrap fixture.
- Confirm exact `chunk_id` survives both `HybridRetriever` and `search_sec_filings` paths and wrapper parity is meaningful after reranking.
- Verify missing embeddings fail dense/hybrid modes rather than degrading or mislabeling; verify model/dimension/hash mismatch failures.
- Prove the five-item smoke run has no network, paid API, Spark, Databricks, model download, or writes outside its output/temp directory.
- Inspect report JSON/Markdown for all required config, strata, CIs, errors, and non-overwrite behavior.
- Confirm stale scripts and `/api/chat/auditable-rag` references are removed/adapted exactly as specified and no useful judge behavior was lost.
- Run all acceptance commands and report `APPROVED` or `CHANGES_REQUESTED` with file:line evidence.

## Delivery constraints

- LF line endings in every created or edited file.
- Do not touch `.agents/dispatch.sh`.
- Preserve production API behavior except the additive `chunk_id` result and the explicit retrieval-mode seam.
- Do not commit the 10,720-row corpus, full embedding sidecar, generated full reports, credentials, caches, or model weights.
- MiMo must commit the implementation.
- MiMo must write `.agents/mimo/VERDICT-rag-eval-harness.md` with changed files, red-green proof, exact commands/results, report paths, PIT leakage totals by all eight configurations, limitations, and commit SHA.
- DeepSeek's later verdict must be `.agents/deepseek/VERDICT-rag-eval-harness.md` with `APPROVED` or `CHANGES_REQUESTED` and file:line evidence.

## Offline data (exported by Claude, gitignored)
- `evals/data/sec_corpus.jsonl`: 10,720 chunks.
- `evals/data/sec_embeddings.npy` (10720×384 float32) + `evals/data/sec_embedding_ids.json`: the stored bge-small vectors in row order.
In a lane worktree these files are NOT present (gitignored). Read them from `/home/jianj/code/qp1-eval/evals/data/` via the env var `RAG_EVAL_DATA_DIR`, defaulting to `evals/data`.
