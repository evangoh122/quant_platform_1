# CHECK: agent prose/retry round 4b (checker: DeepSeek) — re-check of your r4 findings

Read-only; mutations only in `git archive HEAD | tar -x -C /tmp/<dir>` copies. Run WSL commands directly (`wsl -d Ubuntu -- bash -lc '<cmd>'`),
never via PowerShell wrappers or C:\temp scripts. Write .agents/deepseek/VERDICT-agent-prose-retry-r4b.md between
===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Your r4 verdict: .agents/deepseek/VERDICT-agent-prose-retry-r4.md. Fix: latest commit (Claude tiny fix): reject cases with non-registered
names for each rule (`'tool': 'some_unknown_tool'`, `<tool_call>some_unknown_tool</tool_call>`, `<action>retrieve</action>`, `- tool: …`,
`- action: retrieve`) and rule 4 accepts an optional `- `/`* ` list prefix. Claude: 395 passed; rule-2-double-quote-only → 1 failed;
drop rule 3 → 2 failed; drop the list prefix → 2 failed.
Re-run your four mutations (each must now fail a test) and your false-positive list (bullet prose like "- Action items: ..." and
"* tools of the trade: ..." must still be accepted). Run `python3 -m pytest tests/agent tests/api -q`.
