# CHECK: RAG coverage rounds 19 + 19b (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>`. Write .agents/deepseek/VERDICT-rag-coverage-round19.md between
===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Requests: BUILD-rag-coverage-round19.md (multi-CIK overrides; 20-F/40-F/6-K; your r18 runbook + xbrl resolver blockers) and -round19b.md (ownership
group; per-filing conflict recording; repair command). Commits d7f7b89..d1134e2. Claude (WSL, live SEC): XOM dry run → discovered 9 (was 1),
planned 7, no conflict abort; TSM/ASML/SAP/NVO `--forms 20-F,6-K` → discovered 287, planned 154; `pytest tests/rag tests/bronze` → 1172 passed.
Verify each item with a test that fails on the old code (run the mutations named in the requests), plus: dry-run counters are consistent
(planned + skipped vs discovered — explain or flag the XOM numbers 9/7/9), the repair command is idempotent and only touches the override group,
foreign-filer chunking does not break 10-K/10-Q section mapping, and no change to default forms. Run: python3 -m pytest tests/rag tests/bronze -q --timeout 30.
