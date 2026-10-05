# CHECK: agent prose/retry round 2 (checker: DeepSeek)

Read-only on the worktree; mutations only in `git archive HEAD | tar -x -C /tmp/<dir>` copies; never run git inside a copy.
Write .agents/deepseek/VERDICT-agent-prose-retry-r2.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or
"Status: CHANGES_REQUESTED", file:line.

Commit e2a4b3b fixes Codex's three findings (.agents/codex/VERDICT-agent-prose-retry.md); spec .agents/requests/BUILD-agent-prose-retry-r2.md.
MiMo's verdict is a self-report. Claude (WSL): tests/agent + tests/api → 365 passed.

1. `_looks_like_tool_call`: mutate it to always return False → a test fails. Probe false positives on realistic prose answers
   (e.g. "Risk factors: export controls...", "Action: monitor China exposure", text quoting a 10-K heading with a colon). A legitimate
   answer starting with "Action:" being rejected would be a real usability bug — report it and judge severity.
2. Retry feedback: mutate back to include `type(verr).__name__` → a test fails.
3. Audit: drop the validation_retry entry → a test fails. Is the new status `validation_retry` accepted everywhere AuditEntry is persisted
   (Lakebase agent_actions CHECK constraints in db/migrations, any enum/Literal, analytics outbox mappings)? A status that the DB rejects
   at runtime is blocking.
4. Run `python3 -m pytest tests/agent tests/api -q`.
