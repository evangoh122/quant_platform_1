# CHECK: agent plain-prose answers + one corrective retry (checker: DeepSeek)

Read-only on the worktree. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>`; never run git inside a copy.
Write .agents/deepseek/VERDICT-agent-prose-retry.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or
"Status: CHANGES_REQUESTED", every finding with file:line.

Branch `fix/agent-prose-retry` = origin/main + two Claude deadline fixes that were live-validated on the deployed app but
never merged (they landed on fix/agent-in-app after PR #37 merged):
- 867568c accept plain-prose final answers (no tool executes; malformed tool-call JSON still rejected); output budget 2048.
- 8632658 strict tool-arg guidance in the system prompt + ONE corrective retry when the validator rejects an action; still fails closed after the retry.
Files: agent/runtime.py, agent/model_client.py, tests/agent/test_runtime.py. Claude: tests/agent + tests/api → 356 passed.

Check:
1. Safety: prose is accepted ONLY when the output contains no tool-call attempt; anything that looks like a tool call but fails to
   parse/validate must never execute and must not be returned as prose. Show a mutation where prose acceptance swallows a malformed
   tool call → a test fails (if no test fails, that is blocking).
2. Retry: exactly one retry; a second rejection fails closed; the retry cannot bypass the validator, allowlist, role or write scope;
   the rejection text fed back to the model leaks no secrets or internal exceptions. Mutations: allow 2 retries; skip validation on the
   retry; return the first invalid action after the retry → each must fail a test.
3. Writes stay idempotent across a retry (no double save_research_note).
4. Run `python3 -m pytest tests/agent tests/api -q` and report.
