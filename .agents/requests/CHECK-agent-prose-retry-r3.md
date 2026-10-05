# CHECK: agent prose/retry round 3 — CodeRabbit PR #39 findings (checker: DeepSeek)

Read-only; mutations only in `git archive HEAD | tar -x -C /tmp/<dir>` copies. Write .agents/deepseek/VERDICT-agent-prose-retry-r3.md between
===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Spec: .agents/requests/BUILD-agent-prose-retry-r3.md. Commit 53f5c7e (agent/runtime.py `_looks_like_tool_call`: every tool-name occurrence;
quoted "action"/"tool"/"args" key + colon anywhere). Claude: tests/agent + tests/api → 371 passed; the 3 new tests fail on HEAD~1.
1. Mutations: revert to first-occurrence `find` → a test fails; drop `_QUOTED_KEY_COLON_RE` → a test fails.
2. False positives on realistic prose answers: e.g. a reply quoting a filing that contains `"tool":` inside quotes is unlikely, but check
   prose like `The "action": item in the 10-K...`, `Search_sec_filings: ...`, `search_sec_filings (the tool) found...` — judge severity.
3. Run `python3 -m pytest tests/agent tests/api -q`.
