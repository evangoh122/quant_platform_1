# CHECK: post-submission check of fast-tracked merged code (checker: DeepSeek) — gate before Codex's review

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>`. Write .agents/deepseek/VERDICT-post-submission.md between
===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line evidence.
Scope = what is on main now (this worktree = origin/main): #32 + #37 LLM agent (agent/*, api/routes/agent_chat.py, api/services/hybrid_retriever.py
warehouse corpus load, api/main.py warm-up), #34 CDC (db/migrations/004, pipelines/lakebase_analytics.py, analytics API), #33 Lakebase auth
(db/lakebase.py, app.yaml), #36 scripts/publish_baseline_signals.py + frontend SymbolSelect.
Your earlier verdicts: .agents/deepseek/VERDICT-llm-agent.md (1 blocker: REPLAY-INSERTS untested — Claude added tests/agent/test_save_note_idempotency.py)
and VERDICT-analytics-cdc.md (r1; r2 was APPROVED on the CDC branch). Since then Claude made live-integration fixes (typed ChatMessage, no temperature,
list content, partial-index ON CONFLICT, plain-prose final answer, one corrective retry, Delta targets created on first run, SDK token mint).
Verify: (1) the model can never execute a tool without validate_next_action — the prose-final path and the corrective retry cannot bypass it
(mutations: prose path returns a write action; retry skips validation → FAIL); (2) REPLAY-INSERTS now FAILS; (3) CDC r1 blockers still fixed on main;
(4) no secret/token in logs (SDK mint, model client); (5) signals script is PIT (labels only from later snapshots; training rows strictly labelled).
Run: python3 -m pytest -q tests/agent tests/api tests/rubric --timeout 60.
