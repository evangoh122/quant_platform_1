===CODEX VERDICT START===

CHANGES_REQUESTED

DeepSeek prerequisite: `.agents/deepseek/VERDICT-rag-eval-harness-check2.md` says APPROVED.

Blocking findings:

1. `retrieve()` is not equal to `retrieve_mode("hybrid_rerank")`.

   - Production [`retrieve()`](/home/jianj/code/qp1-eval-harness/api/services/hybrid_retriever.py:607) stops after RRF and returns at line 681.
   - [`retrieve_mode("hybrid_rerank")`](/home/jianj/code/qp1-eval-harness/api/services/hybrid_retriever.py:778) additionally calls the reranker.
   - The purported parity test checks only unordered chunk-ID set equality, not result equality or ordering: [`test_rag_eval_retrieval.py:277`](/home/jianj/code/qp1-eval-harness/tests/rag/test_rag_eval_retrieval.py:277).
   - Therefore the requested real-path parity proof fails.

2. Reports expose raw filing text.

   - Every [`RetrievalHit`](/home/jianj/code/qp1-eval-harness/evals/rag_eval/models.py:67) stores raw text at line 75.
   - [`RunReport.to_dict()`](/home/jianj/code/qp1-eval-harness/evals/rag_eval/models.py:160) recursively serializes all item results and hits.
   - [`build_report()`](/home/jianj/code/qp1-eval-harness/evals/rag_eval/report.py:18) retains that complete serialization at line 20; adding sanitized `item_rows` does not remove `item_results`.
   - Consequently JSON reports contain raw filing text. CLI paths are also intentionally recorded through `cli_args`; I found no direct secret serialization.

Independent `/tmp` proofs passed:

- Identity `_pit_filter`: exit 1, `FAIL`, real leakage count 1.
- Clean run: exit 0, `PASS`, leakage 0.
- Injected retrieval error: exit 1, `INCOMPLETE`, leakage 0.
- Hand calculations matched: recall `2/3`, MRR `1/2`, nDCG `0.5307212739772434`.
- Fixed-seed bootstrap was deterministic.
- Sidecar model/dimension propagated into production retriever globals.
- Wrong active model raised `CorpusUnavailableError: Embedding model mismatch`.
- Old `evals/run_eval.py` and `evals/ragas_eval.py` are absent and have no Python imports.
- Generation remains opt-in through [`cli.py:132`](/home/jianj/code/qp1-eval-harness/evals/rag_eval/cli.py:132), with paid calls separately gated.

Test execution:

- `tests/rag` progressed through 72% and then stalled; interrupted.
- Full suite excluding `tests/lakebase` stalled without completion; interrupted.
- Both reversed file-order isolation runs also stalled after partial progress.
- No repository files were edited.

===CODEX VERDICT END===
