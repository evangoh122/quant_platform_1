# CHECK: RAG coverage round 15 (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git inside a copy).
Write .agents/deepseek/VERDICT-rag-coverage-round15.md between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", with file:line evidence.
Request: .agents/requests/BUILD-rag-coverage-round15.md; your r14 verdict: .agents/deepseek/VERDICT-rag-coverage-round14.md. Commit bf6e74f (tests only).
Verify the 3 new value-leak tests cover the SDK success path and both dbutils success paths with caplog at DEBUG + captured stdout/stderr,
and re-run your mutation: add `logger.info("... value=%s", decoded)` at the SDK success line and at each dbutils success line → each new
test FAILS. Confirm no production code changed and rounds 10–14 intact. Run: python3 -m pytest tests/rag tests/bronze -q.
