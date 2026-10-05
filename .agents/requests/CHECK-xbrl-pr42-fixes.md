# CHECK: PR #42 fixes — CI failure + 4 CodeRabbit findings (checker; Codex luna while DeepSeek is out of balance)

Read-only; mutations only in /tmp copies made with `git archive HEAD`. Print the verdict to stdout between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Inputs: .agents/coderabbit-pr42.md, spec .agents/requests/BUILD-xbrl-B1a-pr42-fixes.md. Commits b2454ba, 9adb636, d8e3832, 8f46536. MiMo verdict is a self-report.
Claude: 565 passed with PySpark; with pyspark/databricks.connect imports BLOCKED (mimicking CI): tests/bronze + tests/rag/test_sec_rag_ingest.py → 524 passed, 58 skipped.
1. Finding 1: schema definitions import without PySpark; the contract tests that do not need PySpark still RUN (not skip) without it — check which tests skip without PySpark and whether
   any important contract test is now skipped in CI (blocking if the DDL/StructType contract is no longer checked in CI).
2. Findings 2–4 fixed with tests that fail when reverted (reserve-before-append + release on failure; ALTER verification raises when columns are still missing; PyYAML in serverless deps).
3. Live behaviour unchanged (ingest_sec_companyfacts writes the same columns/types).
