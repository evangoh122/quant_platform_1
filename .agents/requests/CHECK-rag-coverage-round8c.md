# CHECK: rag-coverage round 8c (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git in a cp -r of this worktree).
Write .agents/deepseek/VERDICT-rag-coverage-round8c.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED".
Your round-8b verdict: .agents/deepseek/VERDICT-rag-coverage-round8b.md (4 non-load-bearing tests). Build request: BUILD-rag-coverage-round8c.md. Commit d2f4131.
Rerun YOUR four mutations — each must now FAIL: scalar ticker equality instead of isin; `return len(out_rows)` instead of MERGE metrics (fixture with
candidates ≠ inserted); the coverage SQL — flip the ROW_NUMBER ORDER BY mapped_ts direction AND drop the universe restriction (the DuckDB test must run
the SQL extracted from gold/07, not a copy); concurrent batches — drop one batch's rows → FAILS. No tests deleted/weakened.
Run python3 -m pytest tests/rag tests/bronze -q; pyspark hidden PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps tests/rag.
