# VERDICT: rag-eval-harness-round10 — MiMo
**Status:** APPROVED
**Round:** 10

## Blocking findings
None.

## Non-blocking notes
- 2 pre-existing failures in dense-mode tests (test_eight_configs_produce_results, test_pit_filter_applied_in_dense) due to SentenceTransformer trying to download from huggingface.co which is blocked by the network guard. Not related to round 10 changes.
- 3 collection errors (test_chat_engine, test_graph_rag_engine, test_langgraph_engine) due to missing `api.db` module — pre-existing, not related to round 10.

## Checks run
- `python -m pytest tests/rag/test_rag_eval_retrieval.py tests/rag/test_network_guard.py tests/rag/test_rag_eval_report.py tests/rag/test_rag_eval_corpus.py tests/rag/test_hybrid_retriever.py tests/rag/test_embedding_config.py tests/rag/test_guardrails.py tests/rag/test_guard_mutation_proofs.py tests/rag/test_eval_types.py tests/rag/test_rag_eval_metrics.py -q` → **206 passed, 2 failed (pre-existing), 2 skipped**
- `TestProductionWrapperMatchesHarness` → PASSED (score comparison from wrapper return value, not captured tuples)
- `TestIsLoopbackValidation` (all 4 tests) → PASSED (import real `_is_loopback` from `tests/rag/_netguard.py`)
- All `TestGuardBlocksOutbound` / `TestGuardAllowsLoopback` / `TestGuardAllowsUnixSockets` → PASSED (15 passed,2 skipped for AF_UNIX on Windows)
- `timeout_scoping_proof.py` → PASS (socket.getdefaulttimeout() restored after fixture teardown)
- pytest-timeout in requirements.txt and CI install line confirmed
- `timeout = 30` in pytest.ini is now honored (plugin installed)

## Changes made
1. **agent/tools_retrieval.py:112** — Added `rerank_score` to wrapper output dict so test can compare scores from the return value.
2. **tests/rag/test_rag_eval_retrieval.py:~189-280** — Rewrote TestProductionWrapperMatchesHarness: removed `_prod_reranked_docs` capture inside fake reranker; now compares `(chunk_id, rerank_score)` from wrapper's return value `results_prod` against harness output. Mutation proof: perturbing wrapper output dict score ×1.01 → test FAILS (rel_diff=0.01 >> 1e-9).
3. **.github/workflows/ci.yml:44** — Added `pytest-timeout` to CI pip install line.
4. **requirements.txt:17** — Added `pytest-timeout>=2.2.0`.
5. **tests/rag/conftest.py:85-93** — Scoped `socket.setdefaulttimeout(10)`: save previous value, restore via `request.addfinalizer` on teardown.
6. **tests/rag/_netguard.py** (new) — Extracted `_is_loopback` helper from conftest.py for importability.
7. **tests/rag/conftest.py:7** — Import `_is_loopback` from `tests.rag._netguard` instead of defining inline.
8. **tests/rag/test_network_guard.py:171-221** — `TestIsLoopbackValidation` now imports real `_is_loopback` from `tests.rag._netguard` instead of testing local copies. Mutation: making real function block 127.0.0.2 → `test_loopback_127_0_0_2_allowed` FAILS.

## Mutation proofs
- **M-a (task 1):** Perturbing wrapper output `rerank_score` ×1.01 → `test_search_sec_filings_matches_hybrid_rerank` FAILS. The test uses `pytest.approx(p_score, rel=1e-9)` — a 1% perturbation has rel_diff=0.01 >> 1e-9.
- **M-b (task 4):** Making `_is_loopback` block 127.0.0.2 (e.g. `host in ('127.0.0.1','::1')`) → `test_loopback_127_0_0_2_allowed` FAILS. Tests now import the real function from `_netguard.py`, not a local copy.