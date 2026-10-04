===VERDICT START===
Status: CHANGES_REQUESTED

Blocking findings:

1. Metrics do not deduplicate ranked chunk IDs before scoring. [metrics.py:24](/home/jianj/code/qp1-eval-harness/evals/rag_eval/metrics.py:24), [metrics.py:41](/home/jianj/code/qp1-eval-harness/evals/rag_eval/metrics.py:41), and [metrics.py:62](/home/jianj/code/qp1-eval-harness/evals/rag_eval/metrics.py:62) slice the raw ranking first. Duplicate relevant IDs can produce nDCG greater than 1 (`1.6309` for `["g","g"]` against `["g"]`). An independent 500-case randomized reference found 58 recall, 44 MRR, and 171 nDCG mismatches. Zero-gold answerable rows are also averaged rather than excluded at [metrics.py:291](/home/jianj/code/qp1-eval-harness/evals/rag_eval/metrics.py:291); a perfect row plus a zero-gold row reports recall@5 `0.5`, not `1.0`.

2. Ticker-filter-off is ineffective for hybrid modes. `retrieve_mode()` delegates hybrid modes at [hybrid_retriever.py:778](/home/jianj/code/qp1-eval-harness/api/services/hybrid_retriever.py:778) and [hybrid_retriever.py:790](/home/jianj/code/qp1-eval-harness/api/services/hybrid_retriever.py:790) to methods that restore a ticker from the query at [hybrid_retriever.py:629](/home/jianj/code/qp1-eval-harness/api/services/hybrid_retriever.py:629). Probe results for query “NVIDIA revenue” and `ticker=""`:

   - `bm25`: ticker `""`
   - `dense`: ticker `""`
   - `hybrid_rrf`: ticker `"NVDA"`
   - `hybrid_rerank`: ticker `"NVDA"`

   Thus four of the eight advertised ablations are not independent as specified.

3. The suite is not reliably offline or fast. Dense harness tests call the real embedding provider from [test_rag_eval_retrieval.py:46](/home/jianj/code/qp1-eval-harness/tests/rag/test_rag_eval_retrieval.py:46), while the guard only stubs the reranker at [conftest.py:158](/home/jianj/code/qp1-eval-harness/tests/rag/conftest.py:158). With pytest-timeout installed, seven retrieval tests and `test_verify_entailment_no_model` timed out after Hugging Face retries/model loading.

4. Successful substring-fallback results still omit `chunk_id`; the mapped schema at [tools_retrieval.py:168](/home/jianj/code/qp1-eval-harness/agent/tools_retrieval.py:168) contains no such field. This violates the requirement that every successful `search_sec_filings` result include it.

Verified:

- Hybrid reranking shares `retrieve_and_rerank()` with production, and the parity test compares scores from the wrapper’s returned dictionaries.
- Default reports remove filing text and redact absolute CLI paths.
- CI installs pytest-timeout and configures a 30-second timeout.
- The round-10b timeout-restoration helper is used by the fixture and its regression test is effective.
- Independent PIT reference: 500/500 randomized cases matched.
- Focused relevant tests: 54 passed in 0.56s.
- `git diff --check origin/main...HEAD`: passed.

Full-suite results:

- Exact `python3 -m pytest tests/rag -q`: **412 passed, 20 skipped, 7 failed** in 428.69s. The seven failures were caused by this sandbox rejecting socket creation, including loopback/AF_UNIX.
- `/tmp/h8-venv/bin/python -m pytest tests/rag -q`: **404 passed, 20 skipped, 15 failed** in 292.73s. Seven were the same sandbox socket failures; eight were substantive 30-second model/network-retry timeouts.

Mutation results, all in `/tmp`:

1. Reversed the PIT comparison: hard-gate test failed because future evidence did not raise.
2. Removed default report text stripping: privacy test failed with the filing sentence present.
3. Removed timeout restoration finalizer: regression test failed with `len(finalizers) == 0`.

Repository files were not modified; the working tree remains clean.
===VERDICT END===
