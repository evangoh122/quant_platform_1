===VERDICT START===
# VERDICT: rag-eval-harness — DeepSeek (independent checker, CHECK request)
**Status:** CHANGES_REQUESTED
**Round:** CHECK (HEAD 5d4d999, branch `slice/rag-eval-harness`)

## Summary

The harness is substantially correct and all six requested checks pass in
substance. I re-ran the full corpus end-to-end and reproduced the headline
verbatim: **320/320 evaluated, 0 errors, PIT 0 PASS, recall@5 0.0750**. The one
blocking defect is in PIT-leakage *accounting*: a real leak is converted to an
`ir.error` with `leakage_count = -1`, so the report's PIT gate always prints
`0 PASS` even when chunks leaked. The process exit code still fails (no false
*approval* is possible), but the persisted report — the audit artifact the
harness exists to produce — falsely states "PIT Leakage Gate: PASS" in the exact
scenario the gate is meant to catch.

## Blocking findings

- [evals/rag_eval/retrieve.py:169] `ir.leakage_count = -1  # Sentinel: leakage detected`
  discards the real leaked-chunk count when `assert_no_pit_leakage` raises. The
  CLI then sums leakage with `if ir.leakage_count > 0` (cli.py:231), so `-1` is
  never counted. →
  **Concrete failure:** I disabled the production `_pit_filter` in a `/tmp`
  copy and ran the fixture end-to-end (`python -m evals.rag_eval --adapter jsonl
  --golden tests/rag/fixtures/rag_eval/golden_smoke.jsonl --corpus
  tests/rag/fixtures/rag_eval/corpus_smoke.jsonl --embeddings
  tests/rag/fixtures/rag_eval/embeddings_smoke.npz --mode all --ticker-filter both`).
  30 items leaked (exit code 1, correct), yet the written report JSON has
  `pit_leakage_total: 0`, `pit_leakage_by_config: {}`, and the Markdown file
  renders:

  ```
  ## PIT Leakage Gate
  **Total leakage: 0** PASS
  ```

  with **no Errors section**. The run correctly exits nonzero, but the audit
  report claims a PASS. This violates BUILD item 6 ("Leakage count is the number
  of returned chunks … Sum must be exactly zero and any nonzero value
  raises/fails the run before report success") and item 8 ("PIT leakage
  hard-gate status"). The `if pit_leakage_total > 0: return 1` branch
  (cli.py:314-316) is dead code — leakage is only ever surfaced via the generic
  error path, never as a positive leakage count.

- [evals/rag_eval/cli.py:277 vs 314-321] The report is written *before* the
  leakage/error gate is evaluated, so a failing run still emits a report file
  whose PIT section says PASS. Related to the finding above; fixed together by
  capturing a positive `leakage_count` and/or deriving the Markdown PASS/FAIL
  from both `pit_leakage_total` and the presence of `"PIT leakage"` errors.

## Non-blocking notes

- [agent/tools_retrieval.py:175-186] The `search_sec_filings` *substring
  fallback* result dict omits `chunk_id`, contrary to BUILD item 4 ("every
  successful result includes `chunk_id`"). The hybrid path (line 107) includes
  it; only the degraded fallback path is missing it. Not exercised by the
  harness (which calls `retrieve_mode`, not `search_sec_filings`).
- [api/services/hybrid_retriever.py:555-558] `vector_search` re-implements the
  PIT filter inline instead of calling `_pit_filter`, so the `_pit_filter`
  mutation only disables BM25/hybrid, not dense. The harness leak gate still
  catches dense leakage via `assert_no_pit_leakage`, so this is not a gate
  failure, but it is duplicated, divergent filtering logic worth consolidating.
- [evals/rag_eval/metrics.py:330-335] Bootstrap CIs are computed over 320
  item×mode values (`n=320`), not 80 *item-level* values as BUILD item 6's
  "item-level recall@5" wording implies. Determinism (seed 1729) is correct;
  the population granularity is a minor methodological drift.
- [evals/rag_eval/cli.py:246-271] `reranker_model` / `reranker_revision` /
  `reranker_disabled_reason` are never populated, so the report does not record
  whether the cross-encoder rerank actually ran (BUILD item 8 requires "reranker
  model/revision or disabled reason").
- [evals/rag_eval/cli.py:43-55] `_load_golden` reads `gold_accession_sections`
  and `item_type`, but `evals/data/golden_v1.jsonl` uses scalar
  `gold_accession`/`gold_section` and boolean `answerable`. It happens to work
  because all 80 items are answerable and secondary metrics derive from
  `gold_chunk_ids` → corpus, but the golden-file schema and the loader schema
  have silently drifted.

## Verification of the six CHECK items

1. **PIT gate is real.** `accepted_epoch` → ISO UTC (`corpus.py:24-52`); missing/
   unparseable timestamp counts as violation (`retrieve.py:101-130`,
   `test_rag_eval_round3.py`); errored item → `PIT: INCOMPLETE` + nonzero exit
   (`cli.py:288-292,314-321`). **Mutation proof:** disabling `_pit_filter` →
   30 errors, `FAIL: 30 item(s) had errors`, exit code 1. The gate fails. The
   *reporting* of that failure is the blocking finding above.
2. **Real retrieval path.** `retrieve_mode` (hybrid_retriever.py:683-790) calls
   `bm25_search`, `vector_search`, `rrf_fuse(k=60)`, and `rerank`;
   `test_retrieve_matches_hybrid_rerank_mode` asserts `retrieve()` and
   `retrieve_mode("hybrid_rerank")` agree on the chunk set. Sidecar model/dim
   reach the retriever via `install_offline_corpus` (corpus.py:419-420), same
   state the Delta loader sets. Model-mismatch check is active — I forced
   `_stored_embedding_model = "totally/different-model-v99"` and got
   `CorpusUnavailableError: Embedding model mismatch …` (not disabled).
3. **Metrics.** `recall_at_k`, `reciprocal_rank_at_k`, `ndcg_at_k` match
   hand-computed values (`metrics.py` + my independent spot-checks);
   `bootstrap_ci` is deterministic with seed 1729; per-mode
   `n_evaluated`/`n_errors` correct (40 evaluations = 4 modes × 10 each).
4. **Ablations.** 4 modes × ticker on/off produce 8 distinct *ordered* rankings
   on the fixture; on the full corpus the 4 modes yield distinct
   recall@1 / MRR@10 / nDCG@10 (bm25 0.0250/0.0495/0.0698, dense
   0.0250/0.0493/0.0615, hybrid_rrf 0.0500/0.0624/0.0765, hybrid_rerank
   0.0125/0.0453/0.0638). `retrieve_mode` does **not** silently fall back to
   BM25 (unlike `retrieve()`).
5. **Stale scripts retired.** `evals/run_eval.py` and `evals/ragas_eval.py`
   deleted; `grep -rn 'run_eval\|ragas_eval' --include='*.py'` → no matches;
   `/api/chat/auditable-rag` gone from code; `sec_analyzer.py:27`,
   `docs/MERGE_PLAN.md:191-195`, `docs/FINANCEBENCH_EVAL_PLAN.md` updated;
   generation scorers ported to `generation.py` and OFF by default (no paid
   calls: `test_generation_default_is_disabled`,
   `test_paid_calls_need_explicit_opt_in`).
6. **Test isolation.** `tests/rag/conftest.py:34-70` autouse fixture resets
   embedding + retriever singletons per test; running `tests/rag` forward vs
   reversed order both yield **380 passed, 0 failed** (the 4-skip delta is only
   module-level optional-dependency skips: openai/edgar/langchain_openai/
   scripts, unrelated to the harness).

## Checks run

- `python3 -m pytest -q -p no:cacheprovider tests/rag` → **380 passed, 19 skipped**.
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase` → **659 passed, 67 skipped**.
- `python3 -m evals.rag_eval --adapter jsonl --golden evals/data/golden_v1.jsonl --corpus evals/data/sec_corpus.jsonl --embeddings evals/data/sec_embeddings.npz --ticker-filter on --mode all` → **320 total, 320 evaluated, 0 errors, PIT 0 PASS, recall@5 0.0750** (matches CHECK headline exactly).
- Mutation (`_pit_filter` → no-op, /tmp copy, fixture end-to-end) → **30 errors, exit code 1, "FAIL: 30 item(s) had errors"** (gate fails) — but report renders "Total leakage: 0 PASS" (blocking).
- Model-mismatch probe → `CorpusUnavailableError: Embedding model mismatch` (check not disabled).
- `git diff --check` → clean (only unstaged `.agents/dispatch.sh` mode-bit change, pre-existing).
===VERDICT END===
