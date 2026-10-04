# CHECK: rag-kg round 15 (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git in a cp -r of this worktree).
Write .agents/deepseek/VERDICT-rag-kg-round15.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED".
Reviewer findings: .agents/reviewer/VERDICT-rag-kg-r4.md. Build request: .agents/requests/BUILD-rag-kg-round15.md. Commit 818df88.
1. concept_norm in the find_nodes select; audit EVERY F.col() used after a .select in api/services/sec_knowledge_graph.py is projected. The fake select()
   now really projects and referencing a non-projected column raises (check the fake). Mutation: remove concept_norm from the select → FAILS.
2. max_entities checked via a count BEFORE collecting; spy proves no collect/toLocalIterator when over cap. Mutation: check after collect → FAILS.
3. Legacy guard raises only for concept-bearing nodes with non-empty entity_key/metric and NULL concept_norm; empty-concept nodes pass. Tests both.
4. metric/period validation in agent/tools_retrieval.py rejects before the backend (regex for XBRL concept names: is it anchored with fullmatch/\Z,
   not `$`? "Revenues\n" must be rejected).
No tests deleted/weakened. Run python3 -m pytest tests/rag -q; pyspark hidden PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps.
