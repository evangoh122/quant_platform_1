# CHECK: RAG coverage round 16e (checker: DeepSeek) — restored fallback tests after Codex merge review

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git inside a copy).
Write .agents/deepseek/VERDICT-rag-coverage-round16e.md between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", with file:line evidence.
Codex merge review (.agents/codex/VERDICT-rag-coverage-merge.md) found main's fallback PIT + output-contract tests weakened. Fixes: MiMo r16e
(test_hybrid_retriever.py fallback tests) + Claude tiny fix (the PIT test now asserts unix_timestamp(accepted_ts) and lit(as_of epoch) are
used — MiMo's version only counted .where() calls, so replacing the predicate with lit(True) survived). Tests only; no production change.
Claude (WSL): suite 1128 passed; mutation "PIT predicate → lit(True)" → 1 failed; mutation "drop source_url from fallback output" → 1 failed.
Verify both mutations independently, that the tests now match main-parent strength (`git show 5ba57e4^2:tests/rag/test_hybrid_retriever.py`),
and nothing else changed. Run: python3 -m pytest tests/rag tests/bronze -q.
