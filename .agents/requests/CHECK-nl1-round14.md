# CHECK: NL1 round 14 (checker: DeepSeek)

Read-only. Mutation proofs in /tmp copies (cp -r to /tmp/nl1r14-mut-*). Write .agents/deepseek/VERDICT-nl1-round14.md between ===VERDICT START=== /
===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", findings with file:line, counts, mutation results.
Build request: .agents/requests/BUILD-nl1-round14.md (from Codex .agents/codex/VERDICT-nl1-review2.md). Commits: 8bb7f61..HEAD.
Rerun Codex's surviving mutations — each must now FAIL:
a) remove the benchmark availability from the final GREATEST in serve_relative_performance_v1;
b) replace a rolling window's MAX(information_available_ts) OVER (...) with the current row's information_available_ts;
c) drop the :start_date bound in relative performance (back to inception) — the semantic (DuckDB/extracted-SQL) test must fail;
d) rename close_price → close_price_bogus in the bounded-bars DDL only (both variants) — the registry/view test must fail;
e) restrict coverage enforcement to aggregate only → trend/compare/rank IV tests fail.
Also: item 5 ≤−100% handling uses a window count/bool of invalid rows (not CASE inside SUM); fixture with a −100% day → NULL cumulative +
invalid_return status. test_policy.py:982 was changed deliberately (codified wrong behaviour) — confirm the change is a correction, not a weakening;
no other test deleted/weakened. Schemas in sync.
Run: python3 -m pytest tests/analytics_nl -q; pyspark hidden PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps; python3 -m analytics_nl.export_schemas --check.
