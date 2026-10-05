# VERDICT: agent-prose-retry-r3 — MiMo
**Status:** APPROVED
**Round:** 3

## Blocking findings
- (none)

## Non-blocking notes
- `_QUOTED_KEY_COLON_RE` is case-insensitive; if future tools introduce lowercase-only JSON keys this still catches them.
- `re.finditer` compiles per call inside the loop; negligible for the short texts the agent produces but could be hoisted to a pre-compiled pattern if ALL_TOOLS stabilises.

## Checks run
- `python3 -m pytest tests/agent/test_runtime.py -v` → 44/44 pass
- `python3 -m pytest tests/agent -q` → 66/66 pass
- `python3 -m pytest tests/api -q --timeout=30` → 305/305 pass (67s)

## What was fixed
1. **`_looks_like_tool_call` first-occurrence-only bug** (`runtime.py:242`): `text.find(tool_name)` only checked the first occurrence of each tool name. Replaced with `re.finditer(re.escape(tool_name) + r"\s*[(:]", text)` so every occurrence is inspected. Test: `"I will use search_sec_filings to look. search_sec_filings(symbol='AMD')"` now fails closed (`error_code == "malformed"`).

2. **Brace-free JSON-like fragments slipping through** (`runtime.py:369`): the prose fallback checked `"{" not in plain`, so `["action": "retrieve", "tool": "search_sec_filings"]` (no braces) was accepted as prose. Added `_QUOTED_KEY_COLON_RE = re.compile(r'"(?:action|tool|args)"\s*:', re.IGNORECASE)` to `_looks_like_tool_call`. Quoted key-colon patterns anywhere in the text now fail closed. Plain prose like `"Risk factors: export controls"` and `"Action: monitor China exposure"` still accepted (no double-quoted key).