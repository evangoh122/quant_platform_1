# CHECK: RAG coverage round 12 (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git inside a copy).
Write .agents/deepseek/VERDICT-rag-coverage-round12.md between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", with file:line evidence.
Request: .agents/requests/BUILD-rag-coverage-round12.md (fixes Codex P1 in .agents/codex/VERDICT-rag-coverage-r4.md). Commit: 4415955.
MiMo's self-report is NOT evidence.

Verify:
1. `IngestResult.total_rows_appended` is Optional; in BOTH threaded and serial paths any successful filing with rows_appended=None
   makes the total None; [0,0]→0; [2,5]→7. Drive the real ingest entry point (with fake writers), not just a helper.
2. Every consumer of total_rows_appended / rows_appended is None-safe and never turns None into 0: summary log (renders "unknown"),
   any %d/format, job outputs / notebook exit values / dbutils.jobs.taskValues, audit rows, return values, CLI exit codes.
   Grep all call sites across pipelines/, notebooks/, jobs/, scripts/ and cite them.
3. Runbook idempotency gate text says unknown does NOT pass.
4. Mutation: restore skip-None aggregation (int 0 start, skip None) → named tests FAIL; also red-phase at the parent commit.
Run: python3 -m pytest tests/rag tests/bronze -q.
