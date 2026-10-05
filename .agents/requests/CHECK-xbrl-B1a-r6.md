# CHECK: XBRL B1a round 6 — status code on retry exhaustion (checker: DeepSeek)

Read-only; mutations only in `git archive HEAD | tar -x -C /tmp/<dir>` copies. Shell rule: if a command needs quoting, write it to
`/home/jianj/code/qp1-xbrl/.agentlogs/<name>.sh` and run exactly `wsl -d Ubuntu -- bash /home/jianj/code/qp1-xbrl/.agentlogs/<name>.sh`.
No .ps1/.bat files, no PowerShell wrappers, nothing in C:\temp. Write .agents/deepseek/VERDICT-xbrl-B1a-r6.md between
===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Finding: .agents/codex/VERDICT-xbrl-B1a-r2.md. Fix 80f607a (spec .agents/requests/BUILD-xbrl-B1a-r6.md). Claude: 261 passed.
Mutations, each must fail a test: drop status_code from the exhausted-retry SecClientError; map every failure to "client_error".
Check 403/429/503 exhaustion → manifest http_status and category; non-retried 404 unchanged. Re-run all earlier B1a mutations; offline suite.
