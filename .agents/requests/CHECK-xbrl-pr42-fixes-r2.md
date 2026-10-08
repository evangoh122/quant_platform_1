# CHECK round 2: PR #42 fixes — contract tests run without PySpark (checker; Codex luna while DeepSeek is out of balance)

Read-only; mutations only in /tmp copies made with `git archive HEAD`. Print the verdict to stdout between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Your r1 verdict: .agents/deepseek-fallback/VERDICT-xbrl-pr42-fixes.md (33 contract tests skipped without PySpark). Fix 66ef191. Claude: with pyspark/databricks.connect imports BLOCKED,
tests/bronze + tests/rag/test_sec_rag_ingest.py → 557 passed, 27 skipped (was 524 / 58).
1. Run the same blocked-import run yourself; list what still skips and whether any of it is a contract that CI should check.
2. Mutation WITHOUT PySpark: drop a column from the DDL generator / a _ColumnSpec → a contract test fails.
3. Findings 2–4 from r1 still covered.
