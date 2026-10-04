# CHECK: rag-eval-harness round 12b (checker: DeepSeek) — re-check one fix

Read-only. Your round-12 blocker: lazy verifier init not thread-safe. Claude added a double-checked lock (flag set only after the load attempt) in
api/services/verifier.py and tests/rag/test_verifier.py::test_concurrent_first_use_waits_for_model (latest commit). Re-run YOUR two-thread repro
against the new code (expect no SKIPPED), and confirm the new test FAILS on the old verifier (use `git archive` into /tmp — do NOT cp -r the worktree
and run git commands in the copy). Full suite: python3 -m pytest tests/rag -q.
Write .agents/deepseek/VERDICT-rag-eval-harness-round12b.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED".
