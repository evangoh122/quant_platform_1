# REVIEW round 6: agent prose/retry — broad fail-closed rule (reviewer: Codex)

History: your r3 found spaced positional calls; agy r4 (you were at capacity) found backtick/single-quote/XML shapes
(.agents/reviewer/VERDICT-agent-prose-retry-r4-agy.md). Instead of chasing shapes, round 4 replaced them with one fail-closed rule set in
agent/runtime.py `_looks_like_tool_call`: (1) any registered tool name as a whole word, (2) quoted action/tool/tools/args/arguments/tool_call/
function keys (either quote) + `:`/`=`, (3) XML-ish `<tool|tool_call|function|action|args` tags, (4) line-start `action: <type>`/`tool:`/`args:`
with an optional `- `/`* ` list prefix. Text with `{` still goes the JSON path and fails closed via the validator + one retry.
DeepSeek: r4 CHANGES_REQUESTED (2 non-load-bearing rules) → r4b APPROVED (.agents/deepseek/VERDICT-agent-prose-retry-r4b.md; each rule's
mutation fails a test; 13 realistic prose shapes incl. bullets accepted). Claude: tests/agent + tests/api → 395 passed.
Run `python3 -m pytest tests/agent -q` (tests/api may hang on Databricks SDK retries in your sandbox — report as a sandbox limit). Mutation
proofs only in /tmp via `git archive HEAD | tar -x -C /tmp/<dir>`. Judge: does any tool-call-shaped output still reach the user as prose; is any
realistic finance answer wrongly rejected; is the fail-closed trade-off acceptable. Print the verdict between ===VERDICT START=== /
===VERDICT END=== with "Status: APPROVED" or "Status: CHANGES_REQUESTED" and file:line. Do not edit files.

## Round 6 delta
Your r5 finding (`_TOOL_NAME_RE` case-sensitive) is fixed in the latest commit (Claude one-line tiny fix: `re.IGNORECASE` + two cases
`Search_sec_filings (AMD)`, `SEARCH_SEC_FILINGS(symbol="AMD")`; both fail on HEAD~1). Claude: 397 passed. Confirm it and re-probe.
