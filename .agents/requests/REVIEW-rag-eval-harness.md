# REVIEW: RAG eval harness lane (reviewer: Codex gpt-5.6-sol)

Independent REVIEWER after DeepSeek round 10 (.agents/deepseek/VERDICT-rag-eval-harness-round10.md — its one blocker, a missing
socket-timeout regression test, was added by Claude in the latest commit; verify it). Do NOT edit repo files; mutation proofs in /tmp
copies. Print verdict between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", findings with
file:line, counts, mutation results.

Scope: branch slice/rag-eval-harness vs origin/main (evals/rag_eval/, agent/tools_retrieval.py changes, tests/rag/ harness + guard tests,
pytest.ini, CI changes). Spec: .agents/requests/BUILD-rag-eval-harness.md and the round requests. Earlier Codex review that requested
changes: .agents/codex/VERDICT-*harness* (check resolved).
Review for:
1. Metric correctness: recall@k / MRR / nDCG and the point-in-time leak metric (any retrieved chunk accepted after as_of counts as a
   leak) computed correctly — write your own small reference implementation in /tmp and compare on random rankings.
2. Production parity: the harness uses the SAME retrieve_and_rerank path as production search_sec_filings; scores compared from the
   wrapper's return value.
3. Reports: no filing text unless --include-text; no absolute paths; deterministic output.
4. Tests run offline (network guard) and fast; pytest-timeout honoured in CI.
5. Run 3 mutations of your own.
Run: python3 -m pytest tests/rag -q (use /tmp/h8-venv/bin/python if system python lacks deps)
