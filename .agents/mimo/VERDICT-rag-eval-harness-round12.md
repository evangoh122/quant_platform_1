# VERDICT: rag-eval-harness-round12 — MiMo
**Status:** APPROVED
**Round:** 12

## Blocking findings
(none)

## Non-blocking notes
- Bootstrap now shares the same `_has_gold()` filter as `_avg_metrics` via a single `answerable_scored` list (metrics.py:338).
- Verifier singleton is lazy: `_ensure_model()` deferred to first `verify_entailment` call. Module-level `verifier = Verifier()` no longer triggers CrossEncoder download.
- `_FakeCrossEncoder` in conftest records instances and returns deterministic numpy arrays (entailment bias). Guard test asserts CrossEncoder is patched and no real model loads.
- `test_fake_embedding_provider_active` guards against reverting the embedding fake.

## Checks run
- `python3 -m pytest tests/rag/test_rag_eval_metrics.py::TestBootstrapExcludesZeroGold -xvs` → 2 passed
- `python3 -m pytest tests/rag/test_verifier.py -xvs` → 9 passed
- `python3 -m pytest tests/rag/test_embedding_config.py -xvs` → 7 passed
- `python3 -m pytest tests/rag -q --durations=5` → 438 passed, 19 skipped, 4.01s
- `HF_HUB_OFFLINE=1 python3 -m pytest tests/rag -q --durations=5` → 439 passed, 19 skipped, 3.72s
- Slowest 5 tests (from HF_HUB_OFFLINE run):
  1. test_rag_eval_round5.py::TestDisabledPitFilterReportShowsLeakage::test_report_shows_pass_when_no_leakage — 0.11s
  2. test_rag_eval_report.py::TestCliEndToEndReport::test_report_no_path_leaks — 0.09s
  3. test_rag_eval_round4.py::TestHeadlineStatus::test_error_count_in_per_mode_metrics — 0.08s
  4. test_rag_eval_metrics.py::TestBootstrapIsDeterministic::test_different_seed_differs — 0.07s
  5. test_hybrid_retriever.py::TestAcceptedEpochTimezoneSafe::test_old_code_fails_in_sgt — 0.03s

## Files modified
- `evals/rag_eval/metrics.py` — bootstrap uses `answerable_scored` (same filter as overall)
- `api/services/verifier.py` — lazy `_ensure_model()`, no eager CrossEncoder load
- `tests/rag/conftest.py` — `_FakeCrossEncoder` + `_no_cross_encoder_load` autouse fixture
- `tests/rag/test_verifier.py` — rewritten: fake-aware, entailment/contradiction tests, guard test
- `tests/rag/test_rag_eval_metrics.py` — `TestBootstrapExcludesZeroGold` (2 tests)
- `tests/rag/test_embedding_config.py` — `test_fake_embedding_provider_active` guard