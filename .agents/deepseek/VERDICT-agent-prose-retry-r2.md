===VERDICT START===
# VERDICT: agent-prose-retry-r2 — DeepSeek (checker)
**Status:** APPROVED
**Round:** 2

Checked commit `e2a4b3b` on branch `fix/agent-prose-retry` against `.agents/requests/BUILD-agent-prose-retry-r2.md`. Source read-only on the worktree; all three mutations performed in `/tmp/check-r2-m{1,2,3}` copies created via `git archive HEAD | tar -x -C /tmp/<dir>` (no git run inside copies). Working tree left untouched (`git status --short` empty). MiMo's `VERDICT-agent-prose-retry-r2.md` is a builder self-report; this is the independent check.

## Blocking findings

None.

## Check 1 — `_looks_like_tool_call` (`agent/runtime.py:229-245`)

Mutation applied in `/tmp/check-r2-m1`: replaced the function body with `return False`.

- Result: `tests/agent/test_runtime.py -k ProseFallback` → **2 failed**
  - `test_tool_call_shaped_text_key_value_pairs_rejected`
  - `test_tool_call_shaped_text_with_registered_tool_name_rejected`
- Shipped code: `ProseFallback` → 5 passed. The guard is load-bearing for the two reject paths.

### False-positive probe (realistic prose)

Ran `_looks_like_tool_call` / `_TOOL_CALL_LINE_RE` directly on realistic answers:

| Input | Rejected? |
|---|---|
| `Risk factors: export controls and China tariff exposure remain a headwind.` | no |
| `Item 1A. Risk Factors: Our business is subject to export controls.` | no |
| `We recommend the following action: hold.` | no |
| `Actions we recommend: diversify suppliers.` | no |
| `Tool selection depends on the query.` / `No tool is required...` / `args are not needed...` | no |
| `Action: monitor China exposure and revisit next quarter.` | **yes** |
| `Action: reduce position given the tariff risk.` | **yes** |

**Finding (reported, judged severity = medium, non-blocking):** `agent/runtime.py:224` — a legitimate prose final answer whose first word is `Action:` (e.g. "Action: monitor China exposure") matches `^\s*"?(action|tool|args)"?\s*[:=]` and is rejected with `error_code="malformed"` instead of being returned. Concrete failure: user asks what to do about China exposure; model (in the prose-fallback path) answers "Action: monitor China exposure…"; runtime replies "The model returned an invalid response format." No answer reaches the user.

Why non-blocking: (1) fail-closed — nothing executes, no wrong/unsafe action is returned, so it is a usability regression only, never a safety/correctness regression; (2) the prose path is itself the degraded fallback (the model already failed to emit the JSON the system prompt mandates); (3) the regex is exactly what `BUILD-agent-prose-retry-r2.md` item 1 specified, so the builder is spec-compliant. Suggested tightening for a later round: for the `action` keyword specifically, require the value to be one of the action types (`retrieve|write|final|refuse`), or drop `action` from the leading-keyword list and rely on the `tool`/`args` keywords plus the registered-tool-name-followed-by-`(`/`:` rule, which alone already catch the tool-call examples.

## Check 2 — retry feedback leaks (`agent/runtime.py:398-400`)

Mutation applied in `/tmp/check-r2-m2`: reintroduced `type(verr).__name__` + `str(verr)[:300]` into the feedback string.

- Result: `tests/agent/test_runtime.py -k RetryFeedback` → **1 failed** (`test_retry_feedback_has_no_validation_error`; the pydantic "extra_forbidden" text appears as `extra_forbidden`, not `extra_fields_forbidden`, so the second diagnostic test does not trip on this mutation but still passes on shipped code).
- Shipped code: feedback is the fixed generic string with no exception type and no pydantic diagnostic.

## Check 3 — `validation_retry` audit (`agent/runtime.py:391-396`)

Mutation applied in `/tmp/check-r2-m3`: removed the `validation_retry` `emit` block, keeping `validation_retried = True`.

- Result: `tests/agent/test_runtime.py -k "reject_to_valid or reject_to_reject"` → **2 failed**
  - `test_reject_to_valid_emits_validation_retry_audit`
  - `test_reject_to_reject_emits_retry_then_failed_audit`

### Is `validation_retry` accepted everywhere AuditEntry is persisted?

Audited every place the new value could reach a persisted sink:

- `AuditEntry.action` (`agent/runtime.py:69`) is a free-form `str`, **not** a `Literal`/enum — no schema restriction.
- `agent_actions` (`db/migrations/001_operational_schema.sql:117-126`) has no `CHECK` on `status`, `action_type`, or `tool_name` (all plain `TEXT NOT NULL`); no later migration adds one (grep of `db/migrations/*.sql` for `CHECK` finds only `signals`, `orders`, `accounts`, `analytics_outbox.source_table`/`operation`).
- Analytics outbox `capture_outbox_agent_actions()` (`db/migrations/004_analytics_outbox.sql:434-491`) copies `status`/`action_type` into `after_payload` with no whitelist; `pipelines/lakebase_analytics.py:150-198` groups by `(event_date, tool_name, action_type, status)` with no value filtering.
- In production `api/routes/agent_chat.py:31-38` constructs `AgentRuntime` with **no** `audit_sink`, so it uses `NullAuditSink` (`agent/runtime.py:83-87`); `AuditEntry` is not persisted to Lakebase at all today. The value cannot be rejected by the DB at runtime.

Conclusion: `validation_retry` is accepted everywhere; no blocking DB-rejection path exists.

## Checks run

- `python3 -m pytest tests/agent tests/api -q` → **365 passed** in 61.66s (matches Claude's stated 365)
- `python3 -m pytest tests/agent/test_runtime.py -q -k ProseFallback` (m1) → **2 failed** (guard killed)
- `python3 -m pytest tests/agent/test_runtime.py -q -k RetryFeedback` (m2) → **1 failed** (leak killed)
- `python3 -m pytest tests/agent/test_runtime.py -q -k "reject_to_valid or reject_to_reject"` (m3) → **2 failed** (audit killed)
- `git status --short` on worktree → empty (no mutation leaked)

## Non-blocking notes

- `agent/runtime.py:224` — `action:`-prefixed prose false positive (see Check 1 severity assessment above).
- `agent/runtime.py:391-396` — `validation_retry` emits `result_status="error"` while the second rejection emits `"refused"` (`agent/runtime.py:402-407`); cosmetic inconsistency only, both are valid status strings and neither is constrained by the DB.
===VERDICT END===
