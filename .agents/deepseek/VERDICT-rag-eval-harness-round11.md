# VERDICT: rag-eval-harness-round11 — DeepSeek (checker)
===VERDICT START===
Status: APPROVED
Round: 11

Checker: DeepSeek. Scope: e269bcf..HEAD (6 commits: fa55d8b..9cbb773). Read-only for source;
mutation proofs run in /tmp copies (/tmp/h11-mut-metrics, /tmp/h11-mut-ticker). Python 3.12.3,
pytest 9.1.1, HF_HUB_OFFLINE=1, network guard active.

## Test counts (Linux, WSL, /home/jianj/code/qp1-eval-harness)
- `HF_HUB_OFFLINE=1 python3 -m pytest tests/rag -q` → 432 passed, 19 skipped, 0 failed, 0 timeouts, 3.93s.
- 19 skips are pre-existing and legitimate (optional deps: openai/langchain_openai/edgar; removed
  modules scripts/conjoint; live-network smoke; retired DuckDB review queue). None introduced by round 11.
- Runtime < 120s acceptance met (3.93s); no HuggingFace download or model load occurred.

## Item verification

### 1. Metrics dedup (blocking) — DONE
- `_dedupe_ranking()` at [metrics.py:17](/home/jianj/code/qp1-eval-harness/evals/rag_eval/metrics.py:17) keeps
  first occurrence, preserves order; applied BEFORE top-k in recall [metrics.py:38](/home/jianj/code/qp1-eval-harness/evals/rag_eval/metrics.py:38),
  MRR [metrics.py:56](/home/jianj/code/qp1-eval-harness/evals/rag_eval/metrics.py:56), nDCG [metrics.py:77](/home/jianj/code/qp1-eval-harness/evals/rag_eval/metrics.py:77).
- nDCG ideal DCG = `min(k, |distinct gold|)` [metrics.py:87](/home/jianj/code/qp1-eval-harness/evals/rag_eval/metrics.py:87); result bounded [0,1].
- Zero-gold answerable rows excluded from the mean and counted in `zero_gold_excluded`
  [metrics.py:322-338](/home/jianj/code/qp1-eval-harness/evals/rag_eval/metrics.py:322).
- Explicit cases pass: `["g","g"]` vs `["g"]` → nDCG 1.0 (test asserts `pytest.approx(1.0)`);
  perfect row + zero-gold row → `overall["recall_at_5"] == 1.0` and `zero_gold_excluded == 1`.
- Property test: 4 tests, 500 seeded cases each (`random.Random(1729..1732)`), pool of 20 ids,
  ranking len 0-15, gold len 0-8, k 0-20 → covers duplicates, empty rankings, k > len. Reference
  impls (`_ref_*`) are written inline in the test, NOT imported from production.
- Mutation proof (/tmp/h11-mut-metrics): `_dedupe_ranking` → identity. Result:
  7 failed (`test_recall_matches_reference`, `test_mrr_matches_reference`, `test_ndcg_matches_reference`,
  `test_ndcg_always_bounded`, `test_duplicate_relevant_ids_ndcg_one`, `test_duplicate_non_relevant_ids`,
  `test_ndcg_bounded_zero_one`). Representative failure: `nDCG 1.9199945798893454 out of bounds:
  ['id29','id29',...] gold ['id29'] k=12` (dedupe removed → >1).

### 2. Ticker-filter-off ablation (blocking) — DONE
- `retrieve()` [hybrid_retriever.py:613](/home/jianj/code/qp1-eval-harness/api/services/hybrid_retriever.py:613) and
  `retrieve_and_rerank()` [hybrid_retriever.py:693](/home/jianj/code/qp1-eval-harness/api/services/hybrid_retriever.py:693)
  gain `resolve_ticker: bool = True`; default True → production behaviour unchanged.
- `retrieve_mode()` passes `resolve_ticker=False` for hybrid_rrf [hybrid_retriever.py:791](/home/jianj/code/qp1-eval-harness/api/services/hybrid_retriever.py:791)
  and hybrid_rerank [hybrid_retriever.py:803](/home/jianj/code/qp1-eval-harness/api/services/hybrid_retriever.py:803);
  bm25/dense use `effective_ticker = ticker` directly (no `resolve_ticker_from_query` in those paths).
- Production `search_sec_filings` [tools_retrieval.py:93](/home/jianj/code/qp1-eval-harness/agent/tools_retrieval.py:93)
  calls `retrieve_and_rerank(...)` without `resolve_ticker` → still derives ticker (unchanged).
- Test `test_ticker_filter_off_all_modes` runs all 4 modes with `ticker=""` and asserts non-NVDA
  tickers appear (filter genuinely off).
- Mutation proof (/tmp/h11-mut-ticker): flip the two `resolve_ticker=False` → `True`. Result:
  `test_ticker_filter_off_all_modes` FAILS — `AssertionError: Mode hybrid_rrf: ticker filter OFF but
  only got {'NVDA'}.` (log: `Auto-resolved ticker 'NVDA' from query text`). 1 failed.

### 3. Offline + fast (blocking) — DONE
- `_FakeEmbeddingProvider` (hash-seeded, 384-d, unit-normalized) is installed in the autouse
  `_reset_retriever_singletons` fixture [conftest.py:39](/home/jianj/code/qp1-eval-harness/tests/rag/conftest.py:39).
- Not vacuous: tests that need specific embedding behaviour override `get_embeddings` via their own
  `monkeypatch` (e.g. test_hybrid_retriever.py:175, :2138, :2163 etc.), so the fake provider does not
  suppress those. Dense harness tests assert structure only (non-empty, PIT filter, ticker filter), not
  semantic ordering; no assertion was relaxed this round (see item 5). Config/error tests reload the
  embeddings module (e.g. test_hybrid_retriever.py:2030) so `get_embeddings()` still raises on
  provider=huggingface + no token.
- Fixture `embeddings_smoke.npz` is (10, 384), matching the fake provider dim; dense returns non-empty
  (deterministic) results, so PIT-filter-in-dense is still exercised meaningfully.
- No HF download/model load: full suite 3.93s with `HF_HUB_OFFLINE=1` and the network guard; 0 timeouts.

### 4. Substring-fallback chunk_id (blocking) — DONE
- `search_sec_filings` substring fallback now maps `"chunk_id": r.get("chunk_id", "")`
  [tools_retrieval.py:172](/home/jianj/code/qp1-eval-harness/agent/tools_retrieval.py:172).
- `test_substring_fallback_has_chunk_id` forces the fallback (retriever raises RuntimeError) and asserts
  `r["chunk_id"] == "fallback-chunk-001"` on every successful result. Passes.
- Existing key-schema test strengthened to require `chunk_id` in `expected_keys` (test_hybrid_retriever.py:1404).

### 5. No tests deleted/weakened — DONE
- `git diff e269bcf..HEAD --numstat -- tests/`: conftest +25/-1, test_hybrid_retriever +2/-2,
  test_rag_eval_metrics +172/-1, test_rag_eval_retrieval +88/-1.
- Removed lines: `emb_mod._embeddings = None` → replaced by fake provider (strengthened);
  comment + `expected_keys` set expanded with `chunk_id` (strengthened); two `assert ...` lines were
  only re-added with a trailing newline (no-EOF-newline fix), content unchanged. No assertion weakened.

## Non-blocking notes
- `pytest.ini` `timeout = 30` is not honoured in this local env (pytest-timeout not installed → warning
  "Unknown config option: timeout"). Defense-in-depth still holds via the network guard's 10s socket
  timeout [conftest.py:115](/home/jianj/code/qp1-eval-harness/tests/rag/conftest.py:115); 0 timeouts observed.
  CI installs pytest-timeout (verified in round 10). Consider adding pytest-timeout to the local dev deps.
- Bootstrap CIs at [metrics.py:359-363](/home/jianj/code/qp1-eval-harness/evals/rag_eval/metrics.py:359)
  still include zero-gold rows (recall@5=0.0) while the mean now excludes them — a minor inconsistency,
  out of scope of round-11 blocking items.
- Pydantic `.copy()` deprecation warning in test_rag_eval_retrieval.py:387 (pre-existing).

## Checks run
- `HF_HUB_OFFLINE=1 python3 -m pytest tests/rag -q` → pass (432 passed, 19 skipped, 3.93s).
- `... pytest tests/rag/test_rag_eval_metrics.py::TestDedupPropertyTest ...::TestDeduplicationExplicitCases -v` → 10 passed.
- Mutation 1 (/tmp/h11-mut-metrics, dedupe→identity) → 7 failed (property + explicit cases).
- Mutation 2 (/tmp/h11-mut-ticker, resolve_ticker→True) → test_ticker_filter_off_all_modes failed (hybrid_rrf NVDA-only).
- `git diff e269bcf..HEAD --numstat -- tests/` → only strengthening/newline changes (no weakening).
- `git status` clean (no source modified; /tmp copies + /tmp scripts only).
===VERDICT END===
