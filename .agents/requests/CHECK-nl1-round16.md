# CHECK: NL1 round 16 (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git in a cp -r of this worktree).
Write .agents/deepseek/VERDICT-nl1-round16.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED".
Reviewer findings being fixed: .agents/reviewer/VERDICT-nl1-contracts-r3.md (7 items). Build request: .agents/requests/BUILD-nl1-round16.md. Commits f5eb265..HEAD.
MiMo wrote "6 mutation tests, all pass from archived copy" — ambiguous. YOU must run each mutation against the PRODUCTION DDL/code (not a test helper) and
show the named test FAILS:
1. remove the benchmark availability from serve_relative_performance_v1's final GREATEST; replace the whole GREATEST with one column.
2. relative performance ≤−100%: replace the NULL arm with a computed value; disable the invalid_return status (DuckDB semantic test on the extracted SQL).
3. momentum_20d: remove its availability term from the final GREATEST; LAG on the filtered series.
4. remove `ingest_ts <= :as_of` from a bronze fallback view.
5. LAG before the rn=1 dedup in bounded bars.
6. revert one validator to re.match with `$` → "AAPL\n" accepted → FAILS.
7. coverage check skipped when coverage_stats missing → FAILS; threshold configurable/documented.
No tests deleted/weakened. Run python3 -m pytest tests/analytics_nl -q; pyspark hidden PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps;
python3 -m analytics_nl.export_schemas --check.
