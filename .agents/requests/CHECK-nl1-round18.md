# CHECK: NL1 round 18 (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git in a cp -r of this worktree).
Write .agents/deepseek/VERDICT-nl1-round18.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED".
Your round-17 verdict: .agents/deepseek/VERDICT-nl1-round17.md. Build request: BUILD-nl1-round18.md. Commit 2c305bc.
1. PRODUCTION DOC: COALESCE(return_1d,0)/COALESCE(bench_return,0) removed; `WHERE ... IS NOT NULL` restored; false comment removed. Diff the doc vs round 16
   (pre-17) to confirm the view semantics are back to exclusion + NULL/invalid_return, and nothing else in production changed.
2. LN(0) guard exists ONLY in the to_duckdb() shim, documented. Tests: −100% day → NULL cumulative + invalid_return; masked NULL day excluded (not 0%).
   Mutation: re-add COALESCE(...,0) to the DOC → test (b) FAILS.
3. Adjusted-variant momentum test exists; mutation (WHERE return_1d IS NOT NULL in adjusted with_momentum) → FAILS.
4. Re-run your round-16/17 doc mutations — all still killed.
Run python3 -m pytest tests/analytics_nl -q; pyspark hidden PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps;
python3 -m analytics_nl.export_schemas --check.
