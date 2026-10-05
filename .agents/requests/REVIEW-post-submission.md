# REVIEW: post-submission review of fast-tracked code (reviewer: Codex gpt-5.6-sol)

These merged PRs skipped your review because of the capstone deadline (MiMo built → DeepSeek checked once → Claude live-validated):
#32 LLM agent (agent/contracts.py, agent/model_client.py, agent/runtime.py, api/routes/agent_chat.py, agent/tools_write.py,
db/migrations/005_agent_runtime.sql), #37 agent-in-app fixes (warehouse corpus load in api/services/hybrid_retriever.py, background warm-up
in api/main.py, tolerant JSON parse, plain-prose final answer, one corrective retry), #34 CDC (db/migrations/004_analytics_outbox.sql,
pipelines/lakebase_analytics.py, analytics API), #33 Lakebase auth (db/lakebase.py SDK token mint, PG* env, app.yaml env), #36 signals script
(scripts/publish_baseline_signals.py) + company dropdowns.
Gate: DeepSeek APPROVED in .agents/deepseek/VERDICT-post-submission.md (older per-lane verdicts are superseded by it).
Do NOT edit repo files; mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git inside a copy). Use `git log` / `gh pr view`
for each PR's diff.
Review as the final reviewer: safety of the agent (model can never execute an unvalidated tool; write authorisation + idempotency; prompt-injection
handling of SEC text; the new prose/retry paths cannot bypass validation), CDC correctness (outbox triggers, idempotent watermarked MERGE,
privacy of payloads, first-run table creation), Lakebase auth (no secret leakage, least privilege, correct identity), signals script PIT
correctness and honest labelling. Run your own mutations on the safety properties. Output a prioritised list of findings with file:line, each marked
BLOCKING (must fix) or FOLLOW-UP. Print verdict between ===VERDICT START=== / ===VERDICT END=== with "Status: APPROVED" or "Status: CHANGES_REQUESTED".
Run: python3 -m pytest -q tests/agent tests/api tests/rubric --timeout 60
