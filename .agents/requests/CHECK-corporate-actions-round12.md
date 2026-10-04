# CHECK: corporate-actions round 12 (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git in a cp -r of this worktree).
Write .agents/deepseek/VERDICT-corporate-actions-round12.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED".
Build request: .agents/requests/BUILD-corporate-actions-round12.md (from reviewer .agents/reviewer/VERDICT-corporate-actions-r4.md). Commit 7cdad50,
plus Claude's commit 9b96b34 (notebook header + guard test).
1. New DuckDB tests extract the `_adjusted` view (and its CTEs) from silver/08 at test time and run it — they must RUN here (duckdb installed), not
   skip. Reviewer's surviving mutations must now FAIL: adj_close = close * cum; adj_volume = volume / cum. Cases: two-split cumulative, reverse split,
   ex-date bar on the new basis — exact values asserted.
2. Notebook header guard test fails when the header is removed (Claude verified; reconfirm).
3. Runbook: first-write-wins conflicts documented, WARNING logged when conflict_rows > 0, dry-run default + how to run write mode documented.
No tests deleted/weakened. Run python3 -m pytest -q tests/bronze tests/silver tests/test_security.py -rs (report skip reasons);
pyspark hidden PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps.
