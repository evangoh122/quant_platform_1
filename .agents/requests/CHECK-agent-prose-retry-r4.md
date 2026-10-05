# CHECK: agent prose/retry round 4 — broad fail-closed rule (checker: DeepSeek)

Read-only; mutations only in `git archive HEAD | tar -x -C /tmp/<dir>` copies; never run git inside a copy. If you need WSL, call
`wsl -d Ubuntu -- bash -lc '<cmd>'` directly — never wrap wsl.exe in PowerShell and never write scripts to C:\temp. Write
.agents/deepseek/VERDICT-agent-prose-retry-r4.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or
"Status: CHANGES_REQUESTED", file:line.
Spec: .agents/requests/BUILD-agent-prose-retry-r4.md (+ resume note). Findings fixed: .agents/reviewer/VERDICT-agent-prose-retry-r4-agy.md.
Latest commit on fix/agent-prose-retry. Claude: tests/agent + tests/api → 390 passed; 5 new test cases fail on HEAD~1.
1. Mutations, each must fail a test: drop rule 1 (tool-name word match); make rule 2 double-quote only; drop rule 3 (XML tags); drop rule 4.
2. Probe the agy shapes and a wider set yourself (markdown code fences ```json, `function_call:`, YAML `- tool: x`, `name: search_sec_filings`,
   OpenAI-style `{"name": ..., "arguments": ...}`) — report any that reach the user as prose; judge severity.
3. False positives on realistic finance prose (the accepted list in the spec + your own: "tools of the trade:", "Action items:", quoting
   "function" in a 10-K) — judge severity.
4. Run `python3 -m pytest tests/agent tests/api -q`.
