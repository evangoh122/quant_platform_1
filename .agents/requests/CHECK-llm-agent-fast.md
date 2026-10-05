# CHECK: LLM agent fast-track (checker: DeepSeek) — FAST (submission in ~2.5 h; keep to ~25 min)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>`. Write .agents/deepseek/VERDICT-llm-agent.md between
===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", with file:line evidence.
Request: .agents/requests/BUILD-llm-agent-fast.md (+ docs/rubric/BUILD-llm-agent.md). Commits 80aaa5b..66e832d. Claude: tests/agent+tests/api 340 passed.
Focus ONLY on blocking safety/correctness (this ships today): (1) the model can never execute a tool without `validate_next_action` (allowlist,
arg schema, role, write scope, idempotency); (2) only read tools + save_research_note are exposed — no order/approval tools reachable;
(3) retrieved SEC text is passed as data, not concatenated into system/user instructions; (4) replaying a request does not insert twice;
(5) model failure returns a clear error (no keyword fallback, no unbounded hang — bounded timeout); (6) no secrets/tokens logged.
Re-run mutations MODEL-EXECUTES-DIRECTLY, ORDER-TOOL-EXPOSED, WRITE-WITHOUT-SCOPE, REPLAY-INSERTS → each must FAIL a test.
Run: python3 -m pytest -q tests/agent tests/api --timeout 60.
