# BUILD: agent prose/retry round 4 — replace shape-by-shape regexes with one broad fail-closed rule

You are MiMo. Branch `fix/agent-prose-retry` (stay on it). Read `.agents/reviewer/VERDICT-agent-prose-retry-r4-agy.md`. LF endings, never
touch `.agents/dispatch.sh`, no Databricks. COMMIT your work.

Reviewers keep finding new tool-call shapes (backtick before "(", single-quoted keys, XML tags). Stop chasing shapes. In
agent/runtime.py `_looks_like_tool_call(text)` return True (fail closed) when ANY of:
1. ANY registered tool name (`ALL_TOOLS`) appears anywhere in the text, as a whole word (`\b<name>\b`), in any context (plain, backticks,
   quotes, XML, JSON). Internal snake_case tool names never belong in a user-facing answer.
2. A key `action|tool|tools|args|arguments|tool_call|function` written as a quoted key (single OR double quotes) followed by `:` or `=`.
3. An XML-ish tag `<(tool|tool_call|function|action|args)\b` (case-insensitive).
4. Keep the existing line rule (`action: <retrieve|write|final|refuse>`, `tool:`, `args:` at line start).
Remove `_TOOL_ARGS_OPEN` and the per-occurrence loop (rule 1 replaces them). Keep `{` → malformed as before.
Tests (parametrized; must fail on HEAD where applicable — show the red phase):
- rejected: `` `search_sec_filings`(symbol='AMD') ``, `"search_sec_filings": {"symbol": "AMD"}`, `['action': 'retrieve']`,
  `'tool': 'search_sec_filings'`, `<tool>search_sec_filings</tool>`, `<tool_call>{...}` , `I used search_sec_filings to look.`,
  `search_sec_filings (AMD)`, all existing reject cases.
- accepted: `Action: monitor China exposure and revisit next quarter.`, `Risk factors: export controls remain a concern.`,
  `NVIDIA's 10-K filing discusses export control risks.`, `You should search SEC filings for more information.`,
  `The company's tools: GPUs and CUDA.` (unquoted, mid-line), `The function of the board is oversight.`
Update/replace older tests that asserted the opposite (e.g. "tool name in prose accepted") and say which in the verdict.
Acceptance: `python3 -m pytest tests/agent tests/api -q` green. Verdict `.agents/mimo/VERDICT-agent-prose-retry-r4.md`.
