# CHECK: NL1 round 15 (checker: DeepSeek) — one test

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git in a cp -r of this worktree).
Write .agents/deepseek/VERDICT-nl1-round15.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED".
Your round-14 verdict: .agents/deepseek/VERDICT-nl1-round14.md (mutation b survived). Commit c07aa28.
Rerun YOUR mutation (b): replace realized_vol_20d_info_ts's `MAX(information_available_ts) OVER (... ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)` with
the bare `information_available_ts` → test_output_availability_is_window_max must FAIL; repeat for drawdown_info_ts. Also: change only the window
FRAME of the availability MAX (e.g. 19 → 9 PRECEDING) while the metric keeps 19 → must FAIL (frame matching). Re-run mutations a, c, d, e from round
14 to confirm still killed. No tests deleted/weakened. Run python3 -m pytest tests/analytics_nl -q; pyspark hidden
PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps; python3 -m analytics_nl.export_schemas --check.
