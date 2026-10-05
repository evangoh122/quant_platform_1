# CHECK: NL1 round 19b (checker: DeepSeek) — re-check one fix

Read-only. Your round-19 blocker: the adjusted-return availability test was vacuous (skipped under the DOC mutation). Claude added
tests/analytics_nl/test_ddl.py::test_adjusted_returns_availability_includes_adjusted_source (latest commit), which reads the production DDL.
Rerun Codex's exact mutation in a `git archive HEAD | tar -x -C /tmp/<dir>` copy: `GREATEST(dp.information_available_ts, adj.information_available_ts)
AS information_available_ts` → `dp.information_available_ts AS information_available_ts` (docs ~173) → this test must FAIL (not skip).
Full suite: python3 -m pytest tests/analytics_nl -q. Write .agents/deepseek/VERDICT-nl1-round19b.md between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED".
