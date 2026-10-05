# CHECK: rag-coverage round 10 (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git in a cp -r of this worktree).
Write .agents/deepseek/VERDICT-rag-coverage-round10.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED".
Codex review being fixed: .agents/codex/VERDICT-rag-coverage-review2.md (4×P1, 1×P2). Request: BUILD-rag-coverage-round10.md. Commits since the request.
1. Every createDataFrame in the lane has an explicit schema; the fake Spark now REJECTS all-None schema-less columns (like real PySpark
   CANNOT_DETERMINE_TYPE). Mutation: remove the sec_ingest_log StructType → a test FAILS.
2. Cold start: ensure-table DDL for sec_ingest_log at startup; reader returns "no prior attempts" on a fresh table. Test with the table absent. Runbook name fixed.
3. Pre-existing ownership conflict writes a failed audit row (ownership_conflict) before raising. Mutation: drop the audit write → FAILS.
4. silver/05, silver/06 (and gold/07, pipelines) use catalog/schema placeholders; the runner substitutes them; rendered prod SQL references
   evangoh_capstone_prod everywhere. Mutation: re-hardcode one → FAILS.
5. Missing MERGE metrics → None + WARNING (never len(rows), never silent 0). Tests.
No tests deleted/weakened. Run python3 -m pytest tests/rag tests/bronze -q; pyspark hidden PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps tests/rag.
