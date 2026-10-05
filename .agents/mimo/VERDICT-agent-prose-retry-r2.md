# VERDICT: agent-prose-retry-r2 — MiMo
**Status:** APPROVED
**Round:** 2

## Blocking findings

None.

## Changes implemented

### 1. Prose fallback — reject tool-call-shaped text (`agent/runtime.py:223-245, 366`)

Added `_looks_like_tool_call(text)` that rejects brace-free text matching:
- Lines matching `^\s*"?(action|tool|args)"?\s*[:=]` (case-insensitive)
- Any registered tool name from `ALL_TOOLS` followed by `(` or `:`

The prose fallback now checks `and not _looks_like_tool_call(plain)` before accepting text as a final reply. Plain prose mentioning "10-K" or "search" in natural language is still accepted.

### 2. Retry feedback — fixed string (`agent/runtime.py:398-400`)

Replaced `type(verr).__name__: {str(verr)[:300]}` with a fixed message:
> "Your previous output was not a valid action. Reply with ONE JSON object using only the documented tools and argument keys, or a final answer."

No exception type name, no pydantic diagnostic text leaks to the model.

### 3. validation_retry audit entry (`agent/runtime.py:391-396`)

First validation rejection now emits an `AuditEntry` with `action="validation_retry"` and `validation_outcome=REASON_MALFORMED` before retrying. Second rejection still emits `action="validation_failed"` as before.

## Red phase (new tests failing on current HEAD)

```
FAILED tests/agent/test_runtime.py::TestValidationRetry::test_reject_to_valid_emits_validation_retry_audit
FAILED tests/agent/test_runtime.py::TestValidationRetry::test_reject_to_reject_emits_retry_then_failed_audit
FAILED tests/agent/test_runtime.py::TestProseFallback::test_tool_call_shaped_text_key_value_pairs_rejected
FAILED tests/agent/test_runtime.py::TestProseFallback::test_tool_call_shaped_text_with_registered_tool_name_rejected
FAILED tests/agent/test_runtime.py::TestRetryFeedback::test_retry_feedback_has_no_validation_error
5 failed, 4 passed (prose-mentioning-filing, prose-mentioning-search, tool-name-in-context, pydantic-diagnostic tests passed on HEAD since they test acceptance criteria not yet violated)
```

## Green phase (after fixes)

```
9 passed, 29 deselected
```

## Full agent suite

```
60 passed in 2.30s
```

## API tests

Hang on Databricks SDK metadata retries (same issue as Round 1 — no network in WSL sandbox). Not related to these changes.

## Checks run

- `python3 -m pytest tests/agent/test_runtime.py -q -k "test_tool_call_shaped or test_plain_prose or test_tool_name_in_prose or test_retry_feedback or test_reject_to_valid or test_reject_to_reject"` → **9 passed** (green phase)
- `python3 -m pytest tests/agent -q` → **60 passed** in 2.30s
- `git diff --stat` → `agent/runtime.py (+38/-4), tests/agent/test_runtime.py (+139)`

## Non-blocking notes

- The `_looks_like_tool_call` regex is compiled once at module import time (`re.compile`), no per-call overhead.
- The regex checks line-by-line; multi-line text with a tool-call header on any line is rejected, matching the requirement's "a line matching" wording.
- API tests cannot be run from WSL without Databricks connectivity; agent unit tests fully cover the runtime changes.