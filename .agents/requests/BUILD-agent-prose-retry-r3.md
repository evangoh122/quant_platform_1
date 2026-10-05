# BUILD: agent prose/retry round 3 (CodeRabbit findings on PR #39)

You are MiMo. Branch `fix/agent-prose-retry` (worktree qp1-agentpr; stay on it). LF endings, never touch `.agents/dispatch.sh`,
no Databricks. COMMIT your work.

1. agent/runtime.py `_looks_like_tool_call` (~line 243): it uses `text.find(tool_name)`, so only the FIRST occurrence is checked. Check every
   occurrence (e.g. `re.finditer(re.escape(name) + r"\s*[(:]", text)`). Test: "I will use search_sec_filings to look. search_sec_filings(symbol='AMD')"
   → fails closed (`error_code == "malformed"`).
2. agent/runtime.py prose fallback (~line 369): brace-free JSON-like fragments slip through, e.g. `["action": "retrieve", "tool": "search_sec_filings"]`.
   Also treat as tool-call-shaped: a quoted key `"action"|"tool"|"args"` followed by `:` ANYWHERE in the text (not just at line start). Plain
   prose like `Action: monitor China exposure` and `Risk factors: export controls` must still be accepted (existing tests).
   Tests: the bracket example fails closed; `'"tool": "search_sec_filings"'` inside a sentence fails closed.
Show each new test failing on the current HEAD (red phase). Acceptance: `python3 -m pytest tests/agent tests/api -q` green (WSL).
Verdict `.agents/mimo/VERDICT-agent-prose-retry-r3.md`.
