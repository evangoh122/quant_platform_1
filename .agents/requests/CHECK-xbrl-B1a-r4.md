# CHECK: XBRL B1a round 4 (checker: DeepSeek)

Read-only; mutations only in `git archive HEAD | tar -x -C /tmp/<dir>` copies; never run git inside a copy.
Shell rule: if a command needs quoting, write it to `/home/jianj/code/qp1-xbrl/.agentlogs/<name>.sh` and run exactly
`wsl -d Ubuntu -- bash /home/jianj/code/qp1-xbrl/.agentlogs/<name>.sh`. No .ps1/.bat files, no PowerShell wrappers, nothing in C:\temp.
Write .agents/deepseek/VERDICT-xbrl-B1a-r4.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or
"Status: CHANGES_REQUESTED", file:line.
Your r3 verdict: .agents/deepseek/VERDICT-xbrl-B1a-r3.md. Round 4 commits c2ab7aa..eb7dcd4 (spec .agents/requests/BUILD-xbrl-B1a-r4.md).
MiMo's verdict is a self-report. Claude: 257 passed; no `repr(user_agent)` left in sec_rag_ingest.py.
Mutations, each must fail a test: repr(user_agent) back in the UA error; seen_payloads.add before the write; attempt_count from shared
`client.request_count` deltas; duplicate manifests with default attempt_count; concurrency > 4 workers. Plus all earlier B1a mutations
(placeholder UA, no limiter, overwrite, drop malformed, 403 not retried, http_status removed). Is the per-call attempt tracking thread-safe?
Offline suite green.
