# CHECK: signals PIT round 2 (checker: DeepSeek)

Read-only; mutations only in `git archive HEAD | tar -x -C /tmp/<dir>` copies. Write .agents/deepseek/VERDICT-signals-pit-r2.md between
===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Your round-1 verdict: .agents/deepseek/VERDICT-signals-pit.md. Round 2 commit f013fe2 (spec .agents/requests/BUILD-signals-pit-r2.md).
Claude: tests/ml → 50 passed; F1 mutation (remove same_day from `valid`) → 1 failed (verified).
Re-run all three named mutations from round 1 (each must fail), confirm N1 inline re-implementations are gone, and that the internal sort
keeps results aligned to the caller's index (labels land on the right rows after a shuffle). Run `python3 -m pytest tests/ml -q`.
