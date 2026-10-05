# BUILD: agent prose/retry round 2 (Codex sol CHANGES_REQUESTED)

You are MiMo. Branch `fix/agent-prose-retry` (worktree qp1-agentpr; stay on it, no new branches). Read
`.agents/codex/VERDICT-agent-prose-retry.md` and `.agents/deepseek/VERDICT-agent-prose-retry.md`. LF endings, never touch
`.agents/dispatch.sh`, no Databricks calls. COMMIT your work, one commit per item.

1. agent/runtime.py:341-344 — prose fallback: besides `{`, reject (fail closed, `malformed_json`) text that looks like a tool call:
   a line matching `^\s*"?(action|tool|args)"?\s*[:=]` (case-insensitive), or any registered tool name from the ToolRegistry
   (e.g. `search_sec_filings`, `save_research_note`) followed by `(` or `:`. Plain prose that merely mentions a filing is still accepted.
   Tests: `action: retrieve\ntool: search_sec_filings\nargs: symbol: NVDA` → fails closed, no tool executes; `save_research_note(NVDA, ...)`
   → fails closed; a normal prose answer mentioning "10-K" → accepted.
2. agent/runtime.py:368-370 — retry feedback is a FIXED string (e.g. "Your previous output was not a valid action. Reply with ONE JSON
   object using only the documented tools and argument keys, or a final answer.") — no exception type name, no str(verr). Test that the
   message sent to the model on retry contains neither "ValidationError" nor any pydantic diagnostic text.
3. agent/runtime.py:363-371 — emit a redacted AuditEntry (e.g. status `validation_retry`) for the first rejection before retrying;
   the second rejection still emits `validation_failed`. Test the audit count and statuses for: reject→valid, reject→reject.
Acceptance: `python3 -m pytest tests/agent tests/api -q` green (run from WSL). Show each new test failing on the current HEAD
(red phase) in `.agents/mimo/VERDICT-agent-prose-retry-r2.md`.
