# CHECK: rag-kg round 13 (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git in a cp -r of this worktree).
Write .agents/deepseek/VERDICT-rag-kg-round13.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED".
Your round-12 verdict: .agents/deepseek/VERDICT-rag-kg-round12.md (2 blocking). Round 13 = commit c85169f (migration + NULL guard) and Claude's
earlier commit f609f7a (Spark as-of fixture leads with the future-only node).
1. Rerun YOUR round-12 mutation 1: remove the Spark `df.where(F.exists(...))` → test_spark_limit_1_returns_eligible must FAIL now.
2. ensure_concept_norm_column: ALTER TABLE ADD COLUMNS only when missing, called before the MERGE; re-runnable; the MERGE updates concept_norm on
   matched rows during a full rebuild. Mutation: skip the ALTER → FAILS.
3. NULL concept_norm handling: which option did MiMo pick (structured get_json_object fallback, or "rebuild required" error)? It must not silently drop
   legacy rows and must not reintroduce substring matching. Test exists. Documented in docs/DEPLOYMENT.md.
No tests deleted/weakened. Run python3 -m pytest tests/rag -q; pyspark hidden PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps.
