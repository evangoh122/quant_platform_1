===VERDICT START===
Status: CHANGES_REQUESTED

Blocking findings:

1. Zero-gold rows remain included in bootstrap means. [metrics.py:359](/home/jianj/code/qp1-eval-harness/evals/rag_eval/metrics.py:359) builds bootstrap inputs from every answerable row, unlike the correctly filtered overall aggregation at [metrics.py:328](/home/jianj/code/qp1-eval-harness/evals/rag_eval/metrics.py:328). An independent probe with one perfect row and one zero-gold row produced:

   - `overall.recall_at_5 = 1.0`
   - `zero_gold_excluded = 1`
   - `bootstrap.recall_at_5.mean = 0.5`, `n = 2`

   The report is internally inconsistent and does not fully satisfy zero-gold exclusion.

2. The suite still loads/resolves Hugging Face CrossEncoder models. The fixture only replaces the embedding singleton at [conftest.py:73](/home/jianj/code/qp1-eval-harness/tests/rag/conftest.py:73) and stubs the reranker at [conftest.py:182](/home/jianj/code/qp1-eval-harness/tests/rag/conftest.py:182). It does not cover `Verifier`, which constructs `CrossEncoder` at [verifier.py:21](/home/jianj/code/qp1-eval-harness/api/services/verifier.py:21), including an eager singleton at [verifier.py:72](/home/jianj/code/qp1-eval-harness/api/services/verifier.py:72) and another construction in [test_verifier.py:22](/home/jianj/code/qp1-eval-harness/tests/rag/test_verifier.py:22). `test_verify_entailment_no_model` alone took 46.39 seconds; the functional suite took 97.64 seconds. This violates the explicit “no Hugging Face download or model load” requirement. Reverting the fake embedding assignment to `None` also left the two new dense/hybrid harness tests passing, so they do not guard this offline regression.

Verified:

- Independent 500-case metric reference: zero recall/MRR/nDCG mismatches; duplicate relevant IDs produce nDCG `1.0`.
- “NVIDIA revenue”, ticker filter off: bm25, dense, hybrid_rrf, and hybrid_rerank each returned nine results spanning AAPL, AMD, INTC, NVDA, and QCOM.
- Substring fallback returns the expected `chunk_id`; removing the mapping makes its regression test fail.
- Metric-dedup and hybrid-ticker mutations fail their new tests.
- Focused metric, ticker, fallback, and RRF ranking tests: 19 passed.
- Exact `python3 -m pytest tests/rag -q`: 424 passed, 20 skipped, 7 failed in 97.50s. All seven failures are sandbox-only `PermissionError: Operation not permitted` failures from socket creation, AF_UNIX send, or bind.
- Excluding only network-guard self-tests: 415 passed, 19 skipped.
- `git diff --check e269bcf..HEAD` passed.
- Repository files were not modified; the worktree remains clean.
===VERDICT END===
