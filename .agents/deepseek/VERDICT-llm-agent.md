===VERDICT START===
# VERDICT: llm-agent — DeepSeek (independent fast-track check)

**Status:** CHANGES_REQUESTED
**Round:** 1
**Branch:** `feat/llm-agent` (review scope `80aaa5b..66e832d`; `352ec94` landed mid-review — see notes)

Checker verdict: read-only on the worktree. All four mutations were applied to
disposable `git archive HEAD` copies under `/tmp/qp1-mut/`; no worktree file was
edited. Baseline and mutation results are pasted below.

## Focus-area results (the six blocking questions)

1. Model cannot execute a tool without `validate_next_action` — **VERIFIED**
   (`agent/runtime.py:348` validates before any registry dispatch; M1 catches a bypass).
2. Only read tools + `save_research_note` exposed, no order/approval reachable — **VERIFIED**
   (`agent/contracts.py:177,211-213`; M2 catches adding `create_order_intent`).
3. SEC text passed as data, not concatenated into instructions — **VERIFIED**
   (`agent/runtime.py:183-205` `_build_evidence_section` wraps output in a delimited
   `[BEGIN UNTRUSTED TOOL DATA]` section; the static system prompt never embeds it).
4. Replaying a request does not insert twice — **mechanism correct, but UNTESTED (blocking)**.
5. Model failure returns a clear error, bounded timeout — clear error **VERIFIED**
   (`ModelError` → distinct reason code, no keyword fallback); the timeout is a soft
   post-call check, not a hard bound on the transport call (non-blocking note).
6. No secrets/tokens logged — **VERIFIED** (`agent/model_client.py` logs only `rid`,
   `endpoint`, latency, token counts; never `text`/`messages`/`raw`; audit entries
   carry no prompt/SEC/note text).

## Blocking findings

- [agent/tools_write.py:231-262] The idempotent `save_research_note` upsert
  (`ON CONFLICT (idempotency_key) DO NOTHING` at `:238` + read-back at `:246-253`)
  has **no offline regression test**. The named mutation **REPLAY-INSERTS** — delete
  the `ON CONFLICT … DO NOTHING` line, making the INSERT unconditional — was applied
  to a disposable copy, and `python3 -m pytest -q tests/agent tests/api --timeout 60`
  still reports **340 passed** (mutation undetected). The only runtime "replay" test
  (`tests/agent/test_runtime.py:611` `test_idempotent_replay`) drives a `FakeWriteFn`
  that returns a canned `{"replay": True}` dict and never calls the real
  `save_research_note`; the Lakebase round-trip test
  (`tests/lakebase/test_tools_write.py:92`) performs a single insert and is
  `-m lakebase` (excluded from this check anyway). Concrete failure scenario: a later
  edit drops the `ON CONFLICT` clause or the partial-unique index
  (`db/migrations/005_agent_runtime.sql:21-23`), and replaying an authenticated trader
  request inserts a second research note with no test turning red — contradicting
  focus (4) and the CHECK requirement "REPLAY-INSERTS → must FAIL a test".

## Non-blocking notes

- [agent/model_client.py:110,229] `_WALL_CLOCK_TIMEOUT_SECONDS = 30` (`:32`) is enforced
  only *after* `transport.query()` returns: `DatabricksModelTransport.query` calls
  `client.serving_endpoints.query(...)` with no timeout argument, so the declared "hard
  wall-clock timeout" is a measured check, not a bound on the network call. A hung
  endpoint is only bounded by the SDK's own HTTP timeout. Fails closed (→
  `ModelError("timeout")`, no tool execution), so availability-only, not a safety defect.

- [agent/runtime.py:517] `write_used = True` is set but never read — no second-write
  guard. The spec's "one write" is only indirectly bounded by `max_tool_steps = 3`.
  Impact is limited: every write is gated by the same single-tool `write_authorization`
  and the idempotency key, so a second `save_research_note` in the same trace is a no-op.

- [agent/contracts.py:211-213] `add_to_watchlist` and `get_options_features` are exposed
  beyond the fast-track scope's "ONE write tool / three read tools" wording, but they
  match the binding rubric (item 1: 4 retrieval + 2 low-risk write tools) and both pass
  the same schema/allowlist/role/scope path. Not a blocker.

- [agent/runtime.py:503] The role check reconstructs `AppUser(user_id=user_id, role=role)`
  and drops the request principal's real `authenticated` and `degraded` flags. Currently
  safe because the route gates degraded (`api/routes/agent_chat.py:49`) and public-demo
  (`is_public_demo`), but the reconstructed principal is a fragile coupling.

- [agent/runtime.py:438-455] Evidence binding rejects only *invalid* evidence IDs; a
  `save_research_note` with an empty `evidence_ids` is accepted even when the trace
  produced evidence, so the spec's "bind a note to evidence" is lenient. No unauthorized
  write or exfiltration results.

- Scope drift: commit `352ec94` ("live Databricks serving integration — typed
  ChatMessage …", a coordinator live-run fix) landed after the review scope
  `80aaa5b..66e832d`. It fixes a real transport bug in the reviewed code (plain-dict
  `messages=` to the SDK raises `AttributeError`; `temperature=0` is rejected by some
  endpoints). My mutation copies were extracted from `d0e9447`; the changed lines do not
  intersect the four mutation anchors, so the results below remain valid against `352ec94`
  too (none of the changed files are `contracts.py` or `tools_write.py`).

## Mutation results (disposable copies under /tmp/qp1-mut/)

| Mutation | Change applied | Tests that fail | Result |
| --- | --- | --- | --- |
| MODEL-EXECUTES-DIRECTLY | `runtime.py`: `action = raw_dict` (bypass `validate_next_action`) | `test_unknown_tool`, `test_extra_json_fields` | FAILS ✓ |
| ORDER-TOOL-EXPOSED | `contracts.py`: add `create_order_intent` to write `Literal` + `WRITE_TOOLS` | `test_order_tools_not_in_all`, `test_all_blocked_tools_not_in_all_tools` | FAILS ✓ |
| WRITE-WITHOUT-SCOPE | `runtime.py`: `if False and write_authorization is None/tool !=` | `test_viewer_write_denied`, `test_write_without_authorization_denied` | FAILS ✓ |
| REPLAY-INSERTS | `tools_write.py`: drop `ON CONFLICT (idempotency_key) DO NOTHING` | none — 340 still pass | **NOT caught** ✗ |

## Checks run

```
$ python3 -m pytest -q tests/agent tests/api --timeout 60
340 passed in 56.21s
```

```
$ cd /tmp/qp1-mut/M4-replay && python3 -m pytest -q tests/agent tests/api --timeout 60
340 passed in 61.06s     # REPLAY-INSERTS mutation: no test detects it
```

```
$ cd /tmp/qp1-mut/M1-exec && python3 -m pytest -q tests/agent/test_runtime.py::TestMalformedResponse::test_unknown_tool \
    tests/agent/test_runtime.py::TestMalformedResponse::test_extra_json_fields
2 failed                 # MODEL-EXECUTES-DIRECTLY caught

$ cd /tmp/qp1-mut/M2-order && python3 -m pytest -q tests/agent/test_contracts.py::TestAllowlists::test_order_tools_not_in_all \
    tests/agent/test_runtime.py::TestOrderToolExposure::test_all_blocked_tools_not_in_all_tools
2 failed                 # ORDER-TOOL-EXPOSED caught

$ cd /tmp/qp1-mut/M3-scope && python3 -m pytest -q tests/agent/test_runtime.py::TestWriteAuthorization::test_viewer_write_denied \
    tests/api/test_agent_chat_llm.py::TestAgentChatEndpoint::test_write_without_authorization_denied
2 failed                 # WRITE-WITHOUT-SCOPE caught
```
===VERDICT END===
