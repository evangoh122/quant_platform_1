===VERDICT START===
# VERDICT: agent-prose-retry — DeepSeek (checker)
**Status:** APPROVED
**Round:** 1

Checked branch `fix/agent-prose-retry` (= origin/main + 867568c, 8632658, 263f4b1). Source read-only on the worktree; every mutation performed in `/tmp/agentpr-check` and `/tmp/agentpr-mutations` copies created via `git archive HEAD | tar -x -C /tmp/<dir>` (no git run inside copies). Working tree left untouched.

## Blocking findings

None.

## Safety (check 1) — prose accepted only when there is no tool-call attempt

The prose fallback is `agent/runtime.py:340-346`:

```python
plain = (response.text or "").strip()
if e.code == "malformed_json" and plain and "{" not in plain:
    raw_dict = {"action": "final", "reply": plain[:4000]}
else:
    raw_dict = None
```

- A malformed JSON tool call (e.g. `{"action": "retrieve", "tool": "search_sec_filings", "args": {`) is rejected in `model_client.py:275-291` (`parse_json_response` raises `malformed_json`), and because it contains `{`, the runtime path sets `raw_dict = None` → fails closed. Nothing executes, nothing is returned as prose. Covered by `tests/agent/test_runtime.py::TestMalformedResponse::test_malformed_json`.
- Mutation-reverting test: removing the `"{" not in plain` guard (accept any `malformed_json` as prose) → `test_malformed_json` FAILS (the malformed tool call `{"action": "retrieve", ...` is swallowed as a final reply with `error_code is None`). So the guard is load-bearing and regression-covered.

Result: `test_malformed_json` FAILED under the mutation; PASS on the shipped code.

## Retry (check 2) — exactly one retry, fails closed, no bypass

Retry logic is `agent/runtime.py:361-371`:

- **Exactly one retry**: `validation_retried` is a single per-run boolean (`agent/runtime.py:298`), set True on the first rejection. A second `validate_next_action` rejection hits the `else` branch and fails closed with `REASON_MALFORMED`.
- **Cannot bypass the validator/allowlist/role/write scope**: the retry only `continue`s back to the top of the loop, so the re-proposed action is re-parsed (`parse_json_response`) and re-validated (`validate_next_action`) against the closed `NextAction` schema; tool dispatch still goes through `ToolRegistry` and all write checks (authorization, role, public-demo, symbol/evidence binding) run unchanged.
- **Rejection feedback leak**: `agent/runtime.py:368-370` feeds back `type(verr).__name__` and `str(verr)[:300]` to the *model* (not the user); it is bounded to 300 chars and contains only pydantic schema detail about the model's own output — no secret, DB error, or stack trace. The user-facing result is the generic "The model proposed an invalid action." (`agent/runtime.py:379`).

Mutation-reverting tests (all PASS on shipped code, FAIL on mutated code):

| Mutation | Property broken | Failing tests |
|---|---|---|
| Allow 2 retries (`validation_retries < 2`) | exactly-one-retry | `test_extra_json_fields`, `test_unknown_tool` |
| Skip `validate_next_action` on the retry | retry cannot bypass validator | `test_extra_json_fields` |
| Return the first invalid action after the retry (fail-open) | second rejection fails closed | `test_extra_json_fields`, `test_unknown_tool` |

## Idempotency across retry (check 3) — no double save_research_note

The retry only fires on a `validate_next_action` failure, which occurs strictly *before* execution, so a retried action is never one that already executed. The idempotency key is injected once per request from `write_authorization.idempotency_key` (`agent/runtime.py:543-544`) and is constant for the whole run, so `save_research_note` (`agent/tools_write.py:80-146`) replays on `ON CONFLICT (idempotency_key) DO NOTHING` rather than inserting a second note. No double-write path exists across the retry.

## Checks run

- `python3 -m pytest tests/agent tests/api -q` → **356 passed** in 60.01s (matches the request's stated 356)
- `python3 -m pytest tests/agent/test_runtime.py -q` → **29 passed** in 0.52s
- Mutation A (remove brace guard) → `1 failed` (`test_malformed_json`)
- Mutation B (allow 2 retries) → `2 failed` (`test_extra_json_fields`, `test_unknown_tool`)
- Mutation C (skip validation on retry) → `1 failed` (`test_extra_json_fields`)
- Mutation D (return invalid action after retry) → `2 failed` (`test_extra_json_fields`, `test_unknown_tool`)

## Non-blocking notes

- `agent/runtime.py:341` — the `"{" not in plain` heuristic accepts *any* brace-free text as prose, so a tool-call-shaped output in a non-JSON syntax (e.g. `action: retrieve\ntool: search_sec_filings\nargs: symbol: NVDA`) would be returned as a final reply. No tool executes (still fail-safe), and the model is explicitly instructed to answer "ONE JSON object only", so this is low-probability; consider also rejecting text containing a known tool name / `"action"` key for defense-in-depth.
- `agent/runtime.py:363-371` — the first rejected action that triggers a retry emits no `AuditEntry` (the `validation_failed` entry is only emitted in the non-retry `else` branch at `agent/runtime.py:372`). Minor audit-coverage gap; not a safety defect.
- `agent/runtime.py:369` — rejection feedback includes the pydantic exception type name (`type(verr).__name__`, e.g. `ValidationError`) which is an internal detail fed to the model. It leaks no secret and is model-only/bounded, but a fixed generic message ("invalid tool or argument keys") would fully satisfy the "no internal exceptions" wording of the request.
===VERDICT END===
