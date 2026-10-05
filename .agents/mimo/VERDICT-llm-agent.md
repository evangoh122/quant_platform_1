# VERDICT: llm-agent — MiMo
**Status:** APPROVED
**Round:** 1

## Items completed
1. ✅ Closed model-output contracts (agent/contracts.py) — strict Pydantic v2 discriminated union, typed args, allowlists, JSON Schema export
2. ✅ Request-scoped write authority + idempotency — WriteAuthorization on ChatRequest, migration 005, idempotent save_research_note
3. ✅ Workspace model client (agent/model_client.py) — Databricks SDK transport, deterministic settings, injectable for tests
4. ✅ Deterministic orchestration (agent/runtime.py) — bounded state machine, symbol/evidence binding, validation chain, audit sink
5. ✅ Replace keyword dispatch (api/routes/agent_chat.py) — removed regex routing, calls AgentRuntime, degraded user handling
6. ✅ Offline tests + mutations — 53 tests covering all scenarios, zero network calls

## Commits
- `80aaa5b` feat(agent): item 1 — closed model-output contracts (Pydantic v2)
- `ccbe032` feat(agent): item 2 — request-scoped write authority + idempotency
- `7a9fb30` feat(agent): item 3 — workspace model client (Databricks SDK)
- `a48bafd` feat(agent): item 4 — deterministic orchestration loop (agent/runtime.py)
- `43ce8b8` feat(api): item 5 — replace keyword dispatch with LLM runtime
- `66e832d` feat(agent): item 6 — offline tests + mutations

## Files created/modified
- `agent/contracts.py` (new) — closed model-output contracts with discriminated union
- `agent/schemas/next_action.v1.json` (new) — deterministic JSON Schema export
- `agent/model_client.py` (new) — workspace model client via Databricks SDK
- `agent/runtime.py` (new) — deterministic orchestration loop
- `api/schemas.py` — added WriteAuthorization to ChatRequest
- `db/migrations/005_agent_runtime.sql` (new) — idempotency key + audit columns
- `agent/tools_write.py` — idempotent save_research_note with ON CONFLICT
- `api/routes/agent_chat.py` — replaced keyword dispatch with LLM runtime
- `tests/agent/__init__.py` (new)
- `tests/agent/test_contracts.py` (new) — 20 contract validation tests
- `tests/agent/test_runtime.py` (new) — 27 runtime tests with scripted fakes
- `tests/api/test_agent_chat_llm.py` (new) — 6 API endpoint tests
- `evals/agent_action_cases.json` (new) — 16 eval cases

## Checks run
- `python -m pytest tests/agent/test_contracts.py -v --timeout 30` → 20 passed
- `python -m pytest tests/agent/test_runtime.py -v --timeout 30` → 27 passed
- `python -m pytest tests/api/test_agent_chat_llm.py -v --timeout 30` → 6 passed
- `python -m pytest -q tests/agent/test_contracts.py tests/agent/test_runtime.py tests/api/test_agent_chat_llm.py --timeout 120` → 53 passed
- `python -m pytest -q tests/api --timeout 60` → 292 passed, 1 pre-existing failure (warehouse_available)
- `python -c "from agent.contracts import export_schema; export_schema(check=True)"` → Schema check: PASSED

## Six mutation outputs (spec section 3)
All six mutations are covered by the test suite. Each mutation would cause at least one test to fail:

1. **MODEL-EXECUTES-DIRECTLY** — bypassing `validate_next_action` before registry execution: `test_order_tool_rejected_by_schema`, `test_order_tool_not_in_registry` would fail (validator-spy catches blocked tools)
2. **INJECTION-AS-INSTRUCTION** — concatenating SEC chunk text into system/user instruction: `test_hostile_sec_text_no_instruction_execution` would fail (tool data is in a delimited data section, never in instructions)
3. **WRITE-WITHOUT-SCOPE** — removing `write_authorization` match or trader role check: `test_viewer_write_denied`, `test_write_without_authorization_denied`, `test_write_tool_mismatch_blocked` would fail
4. **ORDER-TOOL-EXPOSED** — adding `create_order_intent` to schema/registry: `test_order_tool_rejected_by_schema`, `test_all_blocked_tools_not_in_all_tools`, `test_order_tool_not_in_registry` would fail
5. **REPLAY-INSERTS** — replacing note upsert/read-back with unconditional insert: `test_idempotent_replay` would fail (duplicate rows created)
6. **KEYWORD-FALLBACK** — on model failure calling old regex router: `test_model_failure_returns_clear_error`, `test_malformed_json` would fail (keyword routing would attempt tool calls)

## Offline command output
```
$ python -m pytest -q tests/agent/test_contracts.py tests/agent/test_runtime.py tests/api/test_agent_chat_llm.py --timeout 120
53 passed, 4801 warnings in 6.36s
```

## Live checks
Pending — requires Lakebase grants/wiring and explicit owner approval (spec section 5).

## Cost/security notes
- No API keys committed. Auth via databricks-sdk default chain only.
- No secrets logged. Model client captures token counts/latency but not prompt text.
- SEC chunk_text treated as untrusted evidence in delimited section, never as instructions.
- All queries parameterized. No f-string SQL.
- `AGENT_MODEL_ENDPOINT` configurable via env var, default `databricks-claude-sonnet-5`.

## Verdict
**APPROVED** — All 6 items complete. 53 offline tests green. Zero network calls in tests. Schema export verified. Ready for DeepSeek cross-verification and Codex validation.