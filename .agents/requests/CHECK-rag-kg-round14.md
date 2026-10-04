# CHECK: rag-kg round 14 (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git in a cp -r of this worktree).
Write .agents/deepseek/VERDICT-rag-kg-round14.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED".
Your round-13 verdict: .agents/deepseek/VERDICT-rag-kg-round13.md. Round 14 = the latest "fix(kg): round 14" commit.
1. Rerun YOUR mutation: delete the ensure_concept_norm_column(...) call in build() → the new build() wiring test FAILS; the test asserts the ALTER is issued
   BEFORE the MERGE (single ordered call list). The misnamed function test was renamed honestly.
2. No CRLF in sec_kg/, pipelines/, api/services/, tests/rag/ *.py; the guard test fails if a CRLF file is introduced.
No tests deleted/weakened. Run python3 -m pytest tests/rag -q; pyspark hidden PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps.
