# CHECK: rag-kg round 12 (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git in a cp -r of this worktree).
Write .agents/deepseek/VERDICT-rag-kg-round12.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED".
Your round-11 verdict: .agents/deepseek/VERDICT-rag-kg-round11.md. Build request: .agents/requests/BUILD-rag-kg-round12.md. Commit 6100382.
1. concept_norm: computed at build with the same normalize_unicode() + lower() as JSONL; in the gold_sec_kg_nodes StructType/DDL and DATA_SCHEMAS.md;
   Spark query uses exact column equality (no properties_json substring anywhere — grep). Rerun YOUR parity harness: a"b, backslash, full-width
   Ｒｅｖｅｎｕｅ, injection `revenue","metric":"netincome` (must match nothing), revenue vs revenues — both stores agree. Mutation: Spark back to
   substring → FAILS.
2. Fake Spark evaluates F.exists for real and _eval RAISES on unknown expressions (confirm no test silently relies on "unknown = True" anymore).
   Spark-store probe: future-only row then eligible row, limit=1 → eligible row. Mutation: remove the Spark df.where(F.exists(...)) → FAILS.
3. Existing nodes built before concept_norm existed: does the query path handle a NULL concept_norm (old rows) — or does a rebuild populate it?
   State the migration requirement.
No tests deleted/weakened. Run python3 -m pytest tests/rag -q; pyspark hidden PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps.
