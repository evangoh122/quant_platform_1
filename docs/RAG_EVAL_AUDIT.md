# RAG Eval Audit — `evals/rag_eval/*`

**Status:** REPORT ONLY. No code in `evals/` was changed (build request
`BUILD-evidently-drift-cleanup`, Part C). All findings below are observations
with `file:line` evidence; fixes are deliberately out of scope for this change.

**Scope reviewed:** `evals/rag_eval/cli.py`, `corpus.py`, `generation.py`,
`metrics.py`, `models.py`, `report.py`, `retrieve.py`, `build_sidecar.py`,
`__main__.py`, `README.md`, plus the harness tests in `tests/rag/test_rag_eval_*.py`
and the gates in `docs/SEC_RAG_COVERAGE_RUNBOOK.md` and `.github/workflows/ci.yml`.
Line numbers refer to the tree this report was produced from.

**Method:** static review of the files above; the harness's own test suite was
run; the CLI was run offline (JSONL adapter, BM25) twice, including once with
`--seed 42` to test seed provenance. Outputs are quoted at the bottom.

---

## 1. Prioritised findings

| ID | Sev | Area | Finding |
| :-- | :-- | :-- | :-- |
| F-1 | **P0** | leakage | The evaluated golden set is not in the repo and the only committed questions are passage-derived (`id == gold_chunk_id`); result quality is unvalidatable. |
| F-2 | **P1** | metrics | Item errors are silently aggregated as `0.0` while zero-gold rows are excluded — headline metrics are depressed without a marker. |
| F-3 | **P1** | determinism | `--seed` never reaches `bootstrap_ci`; report records the user's seed but CIs use 1729 and the Markdown hardcodes `seed=1729`. |
| F-4 | **P1** | determinism | `GoldenItem.as_of=None` falls back to wall-clock `datetime.now`, making PIT filtering/trap labels time-dependent. |
| F-5 | **P1** | leakage | Scorecard JSON embeds `question`, `gold_answer`, `gold_chunk_ids` while only hit text is stripped. |
| F-6 | **P1** | reproducibility | Delta-exported sidecar hashes sorted chunk IDs; the JSONL loader hashes corpus lines — the documented export→offline workflow fails closed. |
| F-7 | **P1** | coverage | None of the runbook's corpus-coverage gates (dedup keys, PIT provenance, embedding completeness, coverage counts, idempotency, 20-F mapping) are measured by the eval. |
| F-8 | **P1** | CLI | `--generation` / `--allow-paid-calls` are parsed but never consumed; README documents a generation mode that the CLI cannot run. |
| F-9 | **P1** | docs | README's "Offline smoke run (no network…)" uses `--mode all`, which downloads the query-embedding and reranker models. |
| F-10 | **P1** | reproducibility | No committed results/baselines; outputs embed `run_id`/`timestamp`/`sys.version`; embedding & reranker revisions unrecorded. |
| F-11 | **P2** | metrics | `candidate_depth_multiplier` is cosmetic — `RetrievalConfig.candidate_depth` is never passed to the retriever. |
| F-12 | **P2** | metrics | `--top-k` unvalidated; metric names stay `*_at_10` regardless of actual retrieval depth. |
| F-13 | **P2** | metrics | Section metrics: gold-only-via-accession items are excluded from `secondary`, missing gold chunks zero the section score. |
| F-14 | **P2** | metrics | Per-type retrieval metrics for `unanswerable`/`point_in_time_trap` are 0 by construction; `per_mode.n_evaluated` counts all types while metrics average answerable only. |
| F-15 | **P2** | docs | `allowed_top_hit` semantics in README differ from the code (forced `False` for unanswerable; membership rule for older-answer traps). |
| F-16 | **P2** | corpus | Duplicate `chunk_id`s are accepted and silently collapsed; sidecar check compares counts, not ID sets. |
| F-17 | **P2** | retrieval | RRF fusion key omits `chunk_id`, collapsing distinct same-text chunks (production-side, affects eval recall). |
| F-18 | **P2** | determinism | Same-second `run_id` collision/overwrite window; local `date.today()` used for report filenames. |
| F-19 | **P2** | tests/docs | README lists 5 of the 9 rag_eval test files; minor fixture/comment drift; `hash()`-based fakes are per-process. |
| F-20 | **P2** | generation | `_parse_score` regex fallback can latch onto arbitrary numbers; the LLM judge protocol has no temperature/seed control. |

---

## 2. Metric correctness

**The core formulas are correct** and match their docstrings/README claims:

- `recall@k` — `evals/rag_eval/metrics.py:30-41`: `len(set(deduped[:k]) & set(gold)) / len(gold)`,
  with `return 0.0` for empty gold (`metrics.py:36-37`) and ranking de-duplicated
  first-occurrence (`metrics.py:17-25`).
- `MRR@10` — `metrics.py:44-61`: `1.0 / (i + 1)` over the deduplicated top-k.
- `nDCG@10` — `metrics.py:64-92`: binary relevance `1 / log2(i + 2)` with
  `ideal_count = min(len(gold), k)`, bounded `[0, 1]`.
- These are pinned by tests, including a 500-case seeded property test against an
  independent reference implementation (`tests/rag/test_rag_eval_metrics.py:184-236`,
  `:368-413`) and a zero-gold mutation proof (`tests/rag/test_rag_eval_metrics.py:302-365`).

Problems found:

- **F-2 (P1).** On any exception, `retrieve_item` only sets `ir.error`
  (`evals/rag_eval/retrieve.py:184-194`), leaving `ir.metrics` empty. Aggregation
  then does `vals = [ir.metrics.get(name, 0.0) for ir in scored]`
  (`metrics.py:328-336`), so an errored item contributes hard zeros to
  `overall`, `per_type`, `per_ticker` and `secondary`, while zero-gold rows are
  excluded (`metrics.py:337-339`). A single flaky item drags every headline
  number to 0 with no marker in the metric table (only `n_errors`, and the exit
  code gate `cli.py:330-335`, reveal it).
- **F-13 (P2).** `_has_gold` checks `gold_chunk_ids` only (`metrics.py:322-324`);
  an item whose gold lives only in `gold_accession_sections` is excluded from the
  `secondary` block (`metrics.py:431`), while a gold chunk id missing from
  `corpus_map` zeroes the section metrics (`metrics.py:109-121`, `:147-155`).
- **F-14 (P2).** Per-type retrieval metrics are reported for `unanswerable` and
  `point_in_time_trap` items where 0 is the correct answer by construction
  (`metrics.py:344-348`), and `per_mode["n_evaluated"]` counts all types while
  the averaged metrics only cover answerable items (`metrics.py:410-417`).
- **F-12 (P2).** `score_item` always names `recall_at_5`, `recall_at_10`,
  `mrr_at_10`, `ndcg_at_10` (`metrics.py:139-143`) regardless of `--top-k`
  (`cli.py:119-122`, unvalidated); `--top-k 5` produces a `recall_at_10` computed
  over 5 candidates, and `top_k_values=[args.top_k]` in the report contradicts
  the metric names (`cli.py:273`).
- **F-11 (P2).** `RetrievalConfig.candidate_depth` (`models.py:95-97`) is never
  passed to the retriever (`retrieve.py:64-77`); the 2x depth is hard-coded in
  `api/services/hybrid_retriever.py` while the report prints
  "Candidate depth multiplier: 2" (`report.py:137`).
- **F-17 (P2).** RRF fusion deduplicates on
  `(ticker, accession, md5(page_content)[:16])` — `api/services/hybrid_retriever.py:905-907` —
  so two distinct gold chunks with identical text in one accession collapse into
  one hit and recall@k is understated; the metrics layer dedups by `chunk_id`
  (`metrics.py:17-25`), so the two layers disagree.
- **F-15 (P2).** README claims `allowed_top_hit` is "True iff top-1 is temporally
  allowed" (`evals/rag_eval/README.md:76`), but the code forces `False` for
  `unanswerable` (`metrics.py:197`) and uses `allowed_older_chunk_ids` membership
  for older-answer traps (`metrics.py:220-225`). The `future_leakage` branch of
  `score_abstention` (`metrics.py:194`, `:216`) is unreachable through the CLI,
  because the PIT gate already raised (`retrieve.py:171-173`).
- Bootstrap percentile indexing uses `int((alpha / 2) * samples)` on the sorted
  means (`metrics.py:282-286`) — a deterministic but non-textbook convention.

## 3. Leakage between corpus and questions

- **F-1 (P0).** The golden set the README evaluates
  (`evals/golden/golden_v1.jsonl`, `README.md:24`, `:36`) **does not exist in the
  repository** (`evals/golden/` is absent; `evals/data/` and `evals/results/`
  are gitignored), so the provenance of any real quality number cannot be
  audited here. The only committed questions —
  `tests/rag/fixtures/rag_eval/golden_smoke.jsonl:1-5` — are written from the
  exact chunks they are retrieved from: the question id equals the gold chunk id
  (`"id": "smoke-001" … "gold_chunk_ids": ["smoke-001"]`) and the question text
  paraphrases `corpus_smoke.jsonl:1` ("NVIDIA reported record revenue of 60.9
  billion dollars for fiscal year 2024…" vs "What was NVIDIA total revenue for
  fiscal year 2024?"). That is the canonical contamination pattern; it is fine
  for plumbing tests, but there is no generator, authoring policy, holdout rule
  or test asserting `gold_answer != chunk text`, so nothing prevents the same
  pattern in the real golden set.
- **F-5 (P1).** `RunReport.to_dict()` is `dataclasses.asdict(self)`
  (`evals/rag_eval/models.py:160-161`), which recursively serialises
  `GoldenItem.question`, `gold_answer`, `gold_chunk_ids`
  (`models.py:22`, `:29`) into the scorecard, while `build_report` strips only
  hit text (`report.py:29-37`) under the claim "text is never written into the
  public scorecard artifact" (`report.py:24-25`). Verified empirically: the run
  quoted in §6 wrote `"gold_answer"` 5 times and full questions into
  `rag_eval_2026-10-21.json`. If reports are shared or committed, the question
  bank leaks.
- L-3 (P2): `generation.py:254-261` feeds `gold_answer` into the context-recall
  judge prompt (`_CONTEXT_RECALL_PROMPT`, `generation.py:113-131`) — circular if
  gold answers are passage-derived (F-1 pattern); moot until generation is wired.
- **F-16 (P2).** The JSONL loader accepts duplicate `chunk_id`s
  (`corpus.py:100-120`) and `cli.py:249` keeps the last; the sidecar check only
  compares counts (`corpus.py:209-213`), so a sidecar with matching count but
  different IDs loads (only `corpus_sha256` can catch it, `corpus.py:236-240`).

*Non-findings (verified clean):* the question text is never indexed into the
corpus (query only — `retrieve.py:40-44`); gold answers never enter corpus
chunks (`corpus.py:409-433`); test fixtures use a hash-of-text fake embedder
independent for questions vs chunks (`tests/rag/conftest.py:56-67`).

## 4. Determinism and seeding

- **F-3 (P1).** `bootstrap_ci(..., seed: int = 1729)` (`metrics.py:249-252`) is
  called from `aggregate_results` **without a seed argument**
  (`metrics.py:363-364`, `:372-375`, `:386-389`), and `aggregate_results` has no
  seed parameter at all. The CLI records `seed=args.seed` (`cli.py:274`; the flag
  is documented as "Random seed for bootstrap", `cli.py:123-126`) and the
  Markdown hardcodes `f"(n={ci['n']}, seed=1729)"` (`report.py:232`).
  Demonstrated: running with `--seed 42` wrote `"seed": 42` in the JSON while
  the Markdown still reported `seed=1729` (see §6). Passing `--seed` is
  therefore a false provenance record, and the CIs are always 1729-seeded.
- **F-4 (P1).** `GoldenItem.as_of_datetime` returns `datetime.now(timezone.utc)`
  when `as_of is None` (`models.py:32-33`; same fallback in the retriever,
  `api/services/hybrid_retriever.py:128-131`). PIT filtering, leakage counting
  (`retrieve.py:101-128`) and trap labels all key off this, so an item without
  `as_of` changes behaviour as calendar time passes. All 5 smoke items pin
  `as_of`, but `_validate_golden` (`cli.py:58-72`) does not require it.
- **F-18 (P2).** Outputs embed wall-clock and machine state:
  `run_id = datetime.now(...).strftime("%Y%m%d_%H%M%S")` (`cli.py:263`),
  `timestamp=datetime.now(...).isoformat()` (`cli.py:277`),
  `environment={"platform": sys.platform, "python": sys.version}`
  (`cli.py:278`), filenames from local `date.today()` (`cli.py:298`,
  `report.py:273-282`). Two runs in the same second share a `run_id` and the
  non-overwrite fallback only appends `run_id` (`report.py:279-280`).
- Otherwise deterministic where it matters: the only RNG is
  `random.Random(seed)` in `bootstrap_ci` (`metrics.py:273`); `per_ticker`
  iterates `sorted(...)`; no `os.listdir`/`glob`/`hash()`/set-ordering affects
  outputs (the `hash()`-based fakes are confined to tests,
  `tests/rag/test_rag_eval_retrieval.py:218`, `:399` — F-19).

## 5. Coverage gaps vs `docs/SEC_RAG_COVERAGE_RUNBOOK.md`

The runbook's gates and the eval are disjoint — the eval measures retrieval
*quality* over whatever corpus it is handed and never *coverage* (F-7):

| Runbook gate | Runbook line(s) | Eval status |
| :-- | :-- | :-- |
| Per-ticker coverage counts (`gold_sec_coverage`) | `SEC_RAG_COVERAGE_RUNBOOK.md:112-115` | Not measured; no gate that the golden set spans the universe. |
| Duplicate-key gates (`record_key`, chunk keys) "must return zero rows" | `:119-120` | Not enforced by the loader (F-16). |
| PIT provenance sanity (`accepted_ts IS NULL`, backfill window, `pit_mismatch`) | `:129-139` | Not measured; eval only checks `accepted_ts > as_of` on returned hits (`retrieve.py:101-128`), so a wrong-but-past `accepted_ts` passes every gate. |
| Embedding completeness for `BAAI/bge-small-en-v1.5` | `:145` | Partial: JSONL+sidecar 1:1 (`corpus.py:209-213`); `DeltaCorpusAdapter` silently skips null vectors (`corpus.py:304-308`). |
| Retrieval smoke (`search_sec_filings` per pilot ticker, `no_coverage` for unknown) | `:154-162` | Covered in tests only (`tests/rag/test_rag_eval_corpus.py:206`); no CLI gate that every ticker returns ≥1 hit. |
| Idempotency (`rows_appended = 0`, `rows=unknown` is failure) | `:202-209` | Not measured; reports carry no ingest `RUN_ID`. |
| Foreign filers 20-F/6-K section mapping | `:239-254` | Not validated; corpus `filing_section` values are trusted. |

## 6. Does it run in CI, and are results reproducible?

- **CI:** yes, the harness tests run in CI — `.github/workflows/ci.yml:55`
  executes `pytest -q -m "not spark and not lakebase and not databricks"` and
  **none of the 9 `tests/rag/test_rag_eval_*.py` files carries a marker**, so all
  127 tests are collected (dependencies installed at `ci.yml:52`). No workflow
  runs the CLI itself, and `generation` has no CI coverage beyond its unit tests.
  The CI install list omits `evidently`-style extras entirely, which is fine
  today because the harness imports nothing optional at module scope.
- **F-10 (P1) reproducibility:** outputs go to `evals/results/`
  (`cli.py:127-130`) which is gitignored, and no baseline/golden-number file
  exists anywhere in `evals/`, so regressions cannot be detected mechanically.
  Bit-identical regeneration is impossible as designed: `run_id`/`timestamp`/
  `sys.version`/`date.today()`/`_git_sha()` all vary (§4), and
  `embedding_revision`/`reranker_revision`/`reranker_model`
  (`models.py:132-136`) are **never populated** by `cli.py:264-292`, so the
  embedding and reranker versions are unpinned (`corpus.py:637` accepts a
  `revision` but stores only `model_name`).
- **F-6 (P1).** `export_delta_embeddings` computes `corpus_sha` from sorted
  chunk IDs (`corpus.py:584-585`) while the loader computes it from the corpus
  JSONL lines (`corpus.py:122-123`) and rejects mismatches
  (`corpus.py:236-240`). The README's documented "Creating a sidecar from Delta"
  → offline run workflow (`README.md:89-97`, `:21-29`) therefore cannot load its
  own export. `build_sidecar._compute_corpus_sha` (`build_sidecar.py:22-31`) and
  `build_local_embeddings` (`corpus.py:633-634`) use the JSONL scheme and agree
  with each other — only the Delta exporter is wrong. It fails closed, so it
  invalidates a workflow rather than silently corrupting numbers.
- **F-8 (P1).** `--generation` (`cli.py:131-134`) and `--allow-paid-calls`
  (`cli.py:135-138`) are parsed but never consumed anywhere in `cli.py`
  (no `args.generation` reference), while README documents a working generation
  mode (`README.md:136-149`). Inside the library the paid-call gate protects the
  judge (`generation.py:235`) but not the agent hook (`generation.py:250`).
- **F-9 (P1).** README's "Offline smoke run (no network, no Spark, no Databricks)"
  (`README.md:7-17`) omits `--mode bm25`, so `--mode all` loads the query
  embedding model (`api/services/embeddings.py:50-54`) and the cross-encoder
  reranker (`api/services/reranker.py:31-49`) — HuggingFace downloads on a cold
  cache. The tests avoid this only via autouse fakes
  (`tests/rag/conftest.py:53-79`, `:194-197`).

---

## 7. Quoted evidence

### Harness test suite (the eval's own tests)

All 9 `tests/rag/test_rag_eval_*.py` files, shared dev venv, offline:

```text
$ python -m pytest -q --timeout=300 \
    tests/rag/test_rag_eval_metrics.py tests/rag/test_rag_eval_corpus.py \
    tests/rag/test_rag_eval_retrieval.py tests/rag/test_rag_eval_round3.py \
    tests/rag/test_rag_eval_round4.py tests/rag/test_rag_eval_round5.py \
    tests/rag/test_rag_eval_report.py tests/rag/test_rag_eval_generation.py \
    tests/rag/test_rag_eval_build_sidecar.py
...
127 passed, 10 warnings in 66.83s
```

Note: with the repository's default `timeout = 30` (`pytest.ini`), the same
selection errors during the cold `transformers` import triggered by
`tests/rag/conftest.py:196` (`_block_network` → `api.services.reranker`); with a
warm import cache (the full-suite CI run) the tests pass. This is a test-harness
startup cost, not a harness bug, but it means a cold targeted run of the rag_eval
tests is not reliable at the default timeout.

### CLI offline run (JSONL adapter, BM25, no network)

```text
$ python -m evals.rag_eval --adapter jsonl \
    --golden tests/rag/fixtures/rag_eval/golden_smoke.jsonl \
    --corpus tests/rag/fixtures/rag_eval/corpus_smoke.jsonl \
    --embeddings tests/rag/fixtures/rag_eval/embeddings_smoke.npz \
    --mode bm25 --ticker-filter off --top-k 5 --output-dir /tmp/opencode/rag-eval-audit
Running 5 items x 1 configs = 5 evaluations...

Reports written:
  JSON: /tmp/opencode/rag-eval-audit/rag_eval_2026-10-21.json
  Markdown: /tmp/opencode/rag-eval-audit/rag_eval_2026-10-21.md

============================================================
  Items: 5 total, 5 evaluated, 0 errors
  PIT Leakage: 0 PASS
  Overall recall@5: 1.0000
  Overall MRR@10: 0.6250
  Overall nDCG@10: 0.7153

  Per-mode breakdown:
    bm25: n_evaluated=5, n_errors=0, recall@5=1.0000
============================================================
```

The recall@5 = 1.0000 above is **not** a quality signal: the smoke questions are
derived from the smoke chunks (F-1), so a lexical retriever cannot miss.

### Seed provenance (F-3)

```text
$ python -m evals.rag_eval ... --mode bm25 --seed 42 --output-dir /tmp/opencode/rag-eval-audit-seed42
$ grep -o '"seed": [0-9]*' /tmp/opencode/rag-eval-audit-seed42/rag_eval_2026-10-21.json | head -1
"seed": 42
$ grep -o 'seed=1729' /tmp/opencode/rag-eval-audit-seed42/rag_eval_2026-10-21.md | head -1
seed=1729
```

The JSON records the user seed while the CI block (and the actual bootstrap RNG)
used 1729.

### Golden-set leakage into the scorecard (F-5)

```text
$ grep -c '"gold_answer"' /tmp/opencode/rag-eval-audit/rag_eval_2026-10-21.json
5
$ grep -o '"question": "[^"]\{0,60\}' /tmp/opencode/rag-eval-audit/rag_eval_2026-10-21.json | head -2
"question": "What was NVIDIA total revenue for fiscal year 2024?
"question": "What are the risk factors for NVIDIA?
```

---

## 8. Recommended fix order (not implemented here)

1. **P0 / F-1:** publish the golden set with a documented authoring process
   (held-out sources, question authors without corpus access, `gold_answer`
   written independently of chunk text) and add a test that fails when a
   question's gold answer is a near-copy of its gold chunk.
2. **P1 / F-2, F-3:** exclude error rows from aggregates (or fail the run), and
   thread `--seed` into `bootstrap_ci`/`aggregate_results` and the Markdown.
3. **P1 / F-4, F-5, F-6:** require `as_of` for every golden item, redact
   `question`/`gold_answer` from the scorecard, and make
   `export_delta_embeddings` hash the corpus the same way the loader does.
4. **P1 / F-7, F-8, F-10:** add the runbook's coverage gates as eval-side
   checks (or a separate `coverage` mode), wire or remove the generation flags,
   and commit a versioned baseline of eval numbers.
