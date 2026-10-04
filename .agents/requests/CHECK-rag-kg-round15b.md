# CHECK: rag-kg round 15b (checker: DeepSeek) — re-check Claude's fixes for your 2 findings

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>`. Write .agents/deepseek/VERDICT-rag-kg-round15b.md between
===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED". Latest commit "fix(kg): fake DataFrame records collect...".
1. Rerun YOUR mutation: move the cap check after the toLocalIterator/collect loops → test_mutation_count_after_collect_fails must FAIL now.
2. "Revenues\n", "2023\n", "2024-Q1\n" rejected by query_sec_facts before the backend (behavioural parametrized test). Note: with the period regex
   reverted to `.match`, the period cases still raise — find out what else rejects them (defense in depth is fine; just document it).
Run python3 -m pytest tests/rag -q.
