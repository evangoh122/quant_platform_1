# CHECK: XBRL B1a round 9 — StructType as the single source of truth (checker: DeepSeek)

Read-only; mutations only in `git archive HEAD | tar -x -C /tmp/<dir>` copies. Shell rule: if quoting is hard, write to
`/home/jianj/code/qp1-xbrl/.agentlogs/<name>.sh` and run `wsl -d Ubuntu -- bash /home/jianj/code/qp1-xbrl/.agentlogs/<name>.sh`. No .ps1/.bat, no PowerShell
wrappers, nothing in C:\temp. Write .agents/deepseek/VERDICT-xbrl-B1a-r9.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or
"Status: CHANGES_REQUESTED", file:line.
Your r7r8 verdict: .agents/deepseek/VERDICT-xbrl-B1a-r7r8.md (DDL could drift from the StructType). Fix acf0ede. Claude: 290 passed; LIVE AMD → 23,826 facts,
no errors (generated DDL works against the existing tables).
Confirm no hand-written column list remains for either table (grep the DDL strings); drop a field from each StructType → contract test fails; the
ALTER-missing-columns path uses the same StructType. Re-run every earlier B1a mutation (UA, limiter, append, malformed, 403, http_status, seen-after-write,
per-call attempts, duplicate attempts, concurrency cap, createDataFrame schema, idempotent ALTER, cache pollution, <1000-entry cache). Offline suite.
