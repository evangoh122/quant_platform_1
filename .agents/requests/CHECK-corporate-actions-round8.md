# CHECK: corporate-actions round 8 (checker: DeepSeek)

Read-only for source. No network/secrets. Mutation proofs in /tmp copies (cp -r to /tmp/ca8-mut-*). Write
.agents/deepseek/VERDICT-corporate-actions-round8.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or
"Status: CHANGES_REQUESTED", findings with file:line, counts, mutation results.
Build request: .agents/requests/BUILD-corporate-actions-round8.md (from your round-7 verdict). Commits: 53aab88..HEAD.
Re-run YOUR round-7 repros exactly:
1. Source filter: real SQL → factor exactly 20.0 with a later non-massive 15.0 row present; your mutation (filter removed) → 15.0 and the test
   FAILS on the mutated SQL.
2. Break logic against REAL SQL (_adjusted, _break_candidates, _classified_breaks extracted from silver/08): unexplained −50% → exactly one
   break row; matching split day → none; mismatched split day → one. Mutation: make the break-candidate predicate always false → FAILS.
   Also check the "mismatched split day" case exists (BUILD item 2c).
3. duckdb in requirements.txt.
4. MiMo says "Bronze timeout is pre-existing (Databricks connectivity)" — run tests/bronze yourself; if any bronze test tries to reach
   Databricks, identify which and whether this branch introduced it.
5. No tests deleted/weakened: git diff 53aab88..HEAD -- tests.
Run: python3 -m pytest -q tests/bronze tests/silver tests/test_security.py; pyspark hidden PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps same.
