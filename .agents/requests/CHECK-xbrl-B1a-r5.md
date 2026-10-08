# CHECK: XBRL B1a round 5 — two tests made mutation-proof (checker: DeepSeek)

Read-only; mutations only in `git archive HEAD | tar -x -C /tmp/<dir>` copies. Shell rule: if a command needs quoting, write it to
`/home/jianj/code/qp1-xbrl/.agentlogs/<name>.sh` and run exactly `wsl -d Ubuntu -- bash /home/jianj/code/qp1-xbrl/.agentlogs/<name>.sh`.
No .ps1/.bat files, no PowerShell wrappers, nothing in C:\temp. Write .agents/deepseek/VERDICT-xbrl-B1a-r5.md between
===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Your r4 verdict: .agents/deepseek/VERDICT-xbrl-B1a-r4.md. Round 5 commit 07b2a87. Claude: 55 passed; removing the skipped_duplicate
`manifest.attempt_count = attempt_count` → 1 failed.
1. Your exact r4 revert (shared `client.request_count - req_before` at the call site and both except blocks) → the concurrent test must FAIL.
   Run it several times; it must fail deterministically (barrier-based, not timing-based).
2. Remove the duplicate-branch assignment → a test fails.
3. Re-run all earlier B1a mutations; offline suite green.
