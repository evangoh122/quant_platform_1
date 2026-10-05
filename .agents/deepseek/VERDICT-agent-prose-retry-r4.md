===VERDICT START===
# VERDICT: agent-prose-retry-r4 — DeepSeek (checker)
**Status:** CHANGES_REQUESTED
**Round:** 4

Checked commit `b613c66` (the r4 fix) on branch `fix/agent-prose-retry` against `.agents/requests/BUILD-agent-prose-retry-r4.md` (+ resume note). Source read-only on the worktree; all four mutations performed in `/tmp/ds-r4-{a,b,c,d}` copies created via `git archive HEAD | tar -x -C /tmp/<dir>` (no git run inside copies). Working tree left untouched. MiMo's `.agents/mimo/VERDICT-agent-prose-retry-r4.md` is a builder self-report; this is the independent check.

## Blocking findings

- `tests/agent/test_runtime.py:848-849` — Rule 3 (XML tag detection, `agent/runtime.py:240-243,267-269`) has **no load-bearing test**. Both shipped XML cases are caught by *other* rules: `<tool>search_sec_filings</tool>` is caught by rule 1 (registered name), and `<tool_call>{...}` is caught by the `{` brace path. Dropping rule 3 (mutation C) fails **zero** tests, yet rule 3 is the *only* guard for brace-free XML with a non-registered payload: `<action>retrieve</action>`, `<tool_call>foo</tool_call>`, `<function>foo</function>`, `<args>x</args>` all reach the user as prose once rule 3 is removed. → Add a parametrized reject case, e.g. `<tool_call>some_unknown_tool</tool_call>` or `<action>retrieve</action>` (brace-free, non-registered name).

- `tests/agent/test_runtime.py:847` — Rule 2 single-quote support (`agent/runtime.py:234-237,264-266`) has **no load-bearing test**. The only single-quoted-key case, `'tool': 'search_sec_filings'`, is caught by rule 1 (registered name). Making rule 2 double-quote-only (mutation B) fails **zero** tests, yet `'tool': 'some_unknown_tool'` reaches the user as prose once the single-quote arm is dropped. → Add a single-quoted-key case with a non-registered value, e.g. `'tool': 'some_unknown_tool'`.

Both are test-coverage gaps (the code is correct and fail-closed today), but the request's check item 1 — "Mutations, each must fail a test" — is not met for 2 of the 4 mutations, and both gaps map to a concrete silent-regression scenario.

## Check 1 — mutation tests (red phase)

Run `python3 -m pytest tests/agent -q` in each mutated copy:

| Mutation | Copy | Result |
|---|---|---|
| drop rule 1 (tool-name word match) | `/tmp/ds-r4-a` | **10 failed**, 75 passed |
| rule 2 → double-quote only | `/tmp/ds-r4-b` | **85 passed** (0 failed) |
| drop rule 3 (XML tags) | `/tmp/ds-r4-c` | **85 passed** (0 failed) |
| drop rule 4 (line-start action/tool/args) | `/tmp/ds-r4-d` | **1 failed**, 84 passed |

Rules 1 and 4 are genuinely load-bearing. Rules 2 (single-quote arm) and 3 are not independently pinned.

## Check 2 — probe agy shapes + wider set (reporting only those that reach the user as prose)

Ran each shape through the full runtime (`AgentRuntime.run`) and recorded whether the raw text reached the user as a final answer (`error_code is None`):

| Shape | Verdict |
|---|---|
| markdown fence ` ```json\n{...}\n``` ` | FAIL-CLOSED (parser extracts JSON; executes; loops to budget) |
| `function_call: search_sec_filings` | FAIL-CLOSED (rule 1) |
| `- tool: search_sec_filings` (YAML, registered) | FAIL-CLOSED (rule 1) |
| `name: search_sec_filings` | FAIL-CLOSED (rule 1) |
| OpenAI `{"name": ..., "arguments": ...}` | FAIL-CLOSED (JSON path) |
| OpenAI `{'name': ..., 'arguments': ...}` | FAIL-CLOSED (`{` → JSON path) |
| `<tool>some_unknown_tool</tool>` / `<action>retrieve</action>` / `<tool_call>foo</tool_call>` / `<args>x</args>` | FAIL-CLOSED (rule 3) |
| `'tool': 'some_unknown_tool'` | FAIL-CLOSED (rule 2 single-quote) |
| `["action": "retrieve"]` / `['action': 'retrieve']` | FAIL-CLOSED |
| `` `search_sec_filings`(symbol='AMD') `` | FAIL-CLOSED (rule 1) |
| **`- tool: some_unknown_tool`** | **REACHED_USER** — raw `- tool: some_unknown_tool` returned as reply |
| **`- action: retrieve`** | **REACHED_USER** — raw `- action: retrieve` returned as reply |

**Severity: LOW, non-blocking.** The only shapes that reach the user are *unquoted* YAML list keys (`- tool:`, `- action:`) paired with a non-registered value. Rule 2 covers quoted keys only and rule 4 requires line-start (the leading `- ` defeats it), so these are out of the round-4 spec. With a registered tool name the same shape is caught by rule 1. Nothing executes — no tool, no data leak — the malformed tool-call text is merely echoed to the user instead of failing closed.

## Check 3 — false positives on realistic finance prose

All accepted (returned as final answer, `error_code is None`) — no false positives:

- `tools of the trade: terminal, Bloomberg, Excel.`
- `Action items: monitor China exposure and revisit next quarter.`
- `The 10-K uses the word "function" to describe the board's role.`
- `The function of the board is oversight.`
- `Risk factors: export controls remain a concern.`
- `The company's tools: GPUs and CUDA.`
- `NVIDIA's 10-K filing discusses export control risks.`
- `You should search SEC filings for more information.`
- `Action: monitor China exposure and revisit next quarter.`

Plus the spec's accepted list (already covered by `test_broad_accepted_prose`). The line-start `action:`/`tool:`/`args:` (rule 4) correctly accepts prose values, and quoted-key rule 2 does not fire on any of the above.

## Checks run

- `python3 -m pytest tests/agent tests/api -q` → **390 passed** in 60.19s (matches Claude's 390)
- `/tmp/ds-r4-a` (drop rule 1): `python3 -m pytest tests/agent -q` → **10 failed**, 75 passed
- `/tmp/ds-r4-b` (rule 2 → double-quote only): → **85 passed**, 0 failed
- `/tmp/ds-r4-c` (drop rule 3): → **85 passed**, 0 failed
- `/tmp/ds-r4-d` (drop rule 4): → **1 failed**, 84 passed
- `/tmp/ds-r4-probe.py` (27 shapes through `AgentRuntime.run`) → results in Check 2/3
- `git status --short` on worktree → empty (no mutation leaked)

## Non-blocking notes

- `- tool: x` / `- action: x` (unquoted YAML list keys, non-registered value) reach the user as prose; out of round-4 spec, low severity (no execution). If desired later, extend rule 2 to unquoted keys or add a list-dash form.
- Rule 1 (`_TOOL_NAME_RE`) is case-sensitive; `Search_sec_filings (AMD)` (capital S) would not match. Pre-existing, unchanged by r4, not in scope.
===VERDICT END===
