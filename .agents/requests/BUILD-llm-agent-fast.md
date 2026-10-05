# BUILD-llm-agent (FAST-TRACK, submission in ~3.5 h) — IMPLEMENT NOW

You are MiMo. Branch `feat/llm-agent` (worktree qp1-agent, based on the approved app branch). Stay on it — do not create/switch branches.
HARD TIME BOX: ~55 minutes. Commit after EACH numbered item. LF endings, never touch `.agents/dispatch.sh`, never weaken tests. No network in tests
(fake the model client). Workspace model endpoint name configurable via env `AGENT_MODEL_ENDPOINT`, default `databricks-claude-sonnet-5`
(Databricks Foundation Model serving; auth via databricks-sdk default chain — no API keys).
Fast-track scope (in order; stop cleanly after a complete item):
  1) spec item 1 — closed model-output contract (pydantic) for the next action: tool name from an allowlist + typed args, or final answer;
  2) spec item 3 — workspace model client (Databricks serving endpoint via databricks-sdk), bounded timeout, no secrets logged;
  3) spec item 4 — deterministic orchestration loop: LLM proposes → `validate_next_action` (allowlist, arg schema, role check, write
     authorization scope, idempotency key) → registry executes → result fed back; max steps; retrieved SEC text passed as DATA (never as
     instructions); ONLY tools: read tools (search_sec_filings, get_market_features, get_latest_signal) + ONE write tool `save_research_note`
     (no order tools);
  4) spec item 2 — request-scoped write authority + idempotency for save_research_note (replay does not insert twice);
  5) spec item 5 — agent_chat.py uses the runtime (no keyword fallback; on model failure return a clear error);
  6) spec item 6 — offline tests + mutations MODEL-EXECUTES-DIRECTLY, INJECTION-AS-INSTRUCTION, WRITE-WITHOUT-SCOPE, ORDER-TOOL-EXPOSED,
     REPLAY-INSERTS, KEYWORD-FALLBACK (paste FAILED output).
Demo target Claude will run live: "Research NVDA's export-control risk and save a research note" → one retrieval tool call then one
save_research_note call, both in the audit trail.
Acceptance: `python3 -m pytest -q -m "not spark and not lakebase and not databricks" --timeout 120` green.
Verdict: .agents/mimo/VERDICT-llm-agent.md (state which items are complete). Full spec (binding for content) follows.

---

# BUILD: constrained workspace-LLM agent runtime

## 0. Assignment and base

MiMo implements this round after `BUILD-analytics-cdc.md` is approved. Base it
on the final app/frontend/deploy work and migration `004`. Do not start
Lakebase, call a real model, or add an external model API key during the build.

The model may propose only the next typed action. It never receives authority
to execute a tool. The deterministic runtime remains the sole executor.

## 1. Numbered changes

1. **Closed model-output contracts -- `agent/contracts.py:1` (new file).**
   - Use strict Pydantic v2 models (`extra="forbid"`, strict scalar types) and a
     discriminated union for exactly: `retrieve`, `write`, `final`, and `refuse`.
   - Retrieval tools are exactly `get_latest_signal`, `get_market_features`,
     `get_options_features`, and `search_sec_filings`. Low-risk write tools are
     exactly `add_to_watchlist` and `save_research_note`.
   - Do not expose order intent, approval, placement, cancellation, broker,
     audit-helper, database, SQL, private function, URL, code, role, user ID, or
     arbitrary kwargs fields anywhere in the model schema.
   - Define typed arguments per tool with normalized symbol, bounded query/note,
     optional evidence IDs, and no `Any`/free dictionaries. Bound the final
     reply and refusal reason. Export/check a deterministic JSON Schema under
     `agent/schemas/next_action.v1.json`.

2. **Request-scoped write authority and idempotency -- `api/schemas.py:121`
   (chat models), `db/migrations/005_agent_runtime.sql:1`,
   `agent/tools_write.py:215` (`save_research_note`; re-resolve after prior
   rounds).**
   - Extend `ChatRequest` with an optional strict `write_authorization` carrying
     exactly one allowed write tool and a caller-supplied bounded idempotency
     key. A read-only request has no write authorization.
   - A model proposal is never authorization. The runtime must match the
     proposed write tool to this request field, the authenticated principal,
     and evidence produced in the same trace. It must still call
     `ensure_role(user, "trader")` and the existing public-demo write guard.
   - Migration `005` adds a nullable unique idempotency key to research notes
     and bounded trace/step/decision fields needed for agent audit records.
     Existing rows remain valid. Reapplying is safe.
   - Make `save_research_note` idempotent for the provided key: a replay returns
     the original note ID and does not create a second note or second effective
     analytics event. Preserve parameterized SQL and transactional audit.

3. **Workspace model client -- `agent/model_client.py:1` (new file).**
   - Query the endpoint named by required `AGENT_MODEL_ENDPOINT` through the
     Databricks SDK default credential chain. Do not read external API keys or
     accept a model/endpoint name from the request.
   - Use deterministic settings (`temperature=0`), bounded input/output tokens,
     a hard wall-clock timeout, a stable client request/trace ID, and no
     streaming for v1. Capture token counts/latency but not prompt text.
   - Require one JSON object and validate it directly against the closed schema.
     Do not strip markdown into validity, `eval`, repair arbitrary JSON, or fall
     back to keyword dispatch. Malformed/timeout/unavailable responses fail
     closed with no tool execution.
   - Make the transport injectable so every offline test uses a scripted fake.

4. **Deterministic orchestration -- `agent/runtime.py:1` (new file).**
   - Implement a bounded state machine: maximum three model calls, three tool
     steps, fixed evidence bytes/rows, and one write. Each turn asks for one
     next action, validates it, executes through a closed registry, appends a
     sanitized result, or stops.
   - Bind symbols to `normalize_symbol`; reject symbol drift between retrieval
     and write. Bind a note to evidence IDs returned in the same trace. A write
     cannot be the first action for the required research-note demo.
   - Treat every retrieval result, especially SEC `chunk_text`, as untrusted
     quoted evidence. Place it in a separately delimited data section, truncate
     it deterministically, retain accession/chunk/source metadata, and tell the
     model it contains no instructions. Never concatenate it into a system or
     user instruction role.
   - Run deterministic validation in this order: schema -> tool allowlist ->
     step/size/time budget -> symbol/evidence binding -> explicit request write
     scope/idempotency -> public-demo guard -> authenticated role -> execution.
   - Record proposed action, validation outcome/reason code, tool result status,
     endpoint, trace ID, and step number through a narrow audit sink. Redact raw
     prompts, SEC text, note text, credentials, and exception strings.
   - The visible response exposes safe tool calls/sources and a concise answer,
     never chain-of-thought or hidden prompts.

5. **Replace keyword dispatch -- `api/routes/agent_chat.py:1`.**
   - Delete `_extract_symbol`/regex routing as orchestration. The endpoint calls
     the new runtime with the authenticated `AppUser` and request contract.
   - Preserve structured unavailable behavior from the app lane. Model failure,
     invalid proposal, retrieval failure, authorization refusal, and write
     failure must be distinguishable by safe reason code and must never become
     an unhandled 500.
   - A degraded Lakebase identity may perform read-only retrieval if the app
     lane permits it, but any write fails fast with 503 and no tool call.

6. **Offline eval and route tests -- `tests/agent/test_runtime.py:1`,
   `tests/agent/test_contracts.py:1`, `tests/api/test_agent_chat_llm.py:1`,
   `evals/agent_action_cases.json:1` (new files).**
   - Script a two-step happy path: user asks to research NVDA and save a note,
     model selects SEC retrieval, then proposes an evidence-bound note, and the
     authorized trader writes exactly once.
   - Include read-only signal/market/SEC cases, unknown symbol, empty retrieval,
     malformed/extra JSON, unknown tool, oversized arguments, endpoint timeout,
     tool exception, viewer write, degraded write, public demo, replay, symbol
     drift, and a model attempt to call every order/private tool.
   - Injection fixtures must include hostile user text and hostile SEC text such
     as instructions to reveal prompts, change role, call a write, approve an
     order, or ignore previous rules. Assert no unauthorized write/tool call and
     a stable refusal/validation code.
   - Assert audit records are emitted for accepted/refused/failed proposals but
     contain none of the hostile text, note body, raw model response, or secret.

## 2. Tests that must fail on the current code

Run the new tests in a temporary clean checkout before implementation. They
must execute against current `api/routes/agent_chat.py` and prove:

- no model transport is called because the route is keyword-based;
- arbitrary prose containing `watch` or `note` can select a write without a
  typed model proposal/request-scoped idempotency contract;
- a two-turn retrieval-then-write plan and strict model schema do not exist;
- malformed/unknown model actions have no fail-closed validator; and
- research-note replay can create a second row.

Collection failure for the new modules is expected but is not sufficient; keep
at least two route/tool tests that import existing code and fail behaviorally.

## 3. Named checker mutations

DeepSeek applies these in disposable copies:

1. **MODEL-EXECUTES-DIRECTLY:** bypass `validate_next_action` before registry
   execution; the validator-spy test must fail and no write may occur.
2. **INJECTION-AS-INSTRUCTION:** concatenate SEC chunk text into the system/user
   instruction message; the role/delimiter test must fail.
3. **WRITE-WITHOUT-SCOPE:** remove the `write_authorization` match or trader
   role check; viewer/no-scope tests must observe the attempted write and fail.
4. **ORDER-TOOL-EXPOSED:** add `create_order_intent` or a private helper to the
   schema/registry; recursive schema and registry tests must fail.
5. **REPLAY-INSERTS:** replace note upsert/read-back with unconditional insert;
   idempotency and audit-count tests must fail.
6. **KEYWORD-FALLBACK:** on model failure call the old regex router; timeout and
   malformed-response tests must detect a tool call and fail.

## 4. Offline acceptance

```bash
python3 -m pytest -q \
  tests/agent/test_contracts.py \
  tests/agent/test_runtime.py \
  tests/api/test_agent_chat_llm.py \
  tests/lakebase/test_tools_write.py \
  tests/lakebase/test_public_demo_write_guard.py
python3 -m pytest -q tests/api
python3 -m agent.export_schemas --check
```

All tests use fake model/retrieval/write/audit transports. Assert zero network
calls and zero live credentials. No external model SDK dependency is needed;
use the already-required Databricks SDK.

## 5. Exact Claude live checks

Run only after round 3 grants/wiring and explicit owner approval for Lakebase
and app compute:

1. Confirm the configured `AGENT_MODEL_ENDPOINT` is an existing workspace
   endpoint and the app service principal has only `CAN_QUERY`.
2. From the deployed URL with a viewer principal, ask for an NVDA SEC research
   summary. Prove the response shows a model-selected retrieval tool and source
   metadata, and no write/audit failure leaks internals.
3. As that viewer, send a forged `write_authorization`; expect 403, no note, and
   a refused audit decision.
4. As a dedicated trader, send `research NVDA, then save a research note` with
   `write_authorization.tool=save_research_note` and a unique idempotency key.
   Prove the visible sequence is retrieval then write, capture trace/note/action
   IDs, and query Lakebase for exactly one note plus redacted audit rows.
5. Replay the identical request/idempotency key. Prove the same note ID returns,
   note count stays one, and no duplicate effective outbox/analytics event is
   created after the analytics job runs.
6. Seed or mock a retrievable SEC chunk containing an instruction to place an
   order/reveal the prompt. With no write authorization, prove only the allowed
   retrieval/final/refusal path occurs. Query audit rows for zero forbidden tool
   names and no hostile text.
7. Record endpoint latency/token usage, app trace ID, audit IDs, and safe
   screenshots/output. Stop app/Lakebase by default after the round-3 smoke.

## 6. Handoff

Use LF endings. Do not touch `.agents/dispatch.sh`, order/execution guardrail
semantics, RAG ingestion, or strategy files. Commit and write
`.agents/mimo/VERDICT-rubric-llm-agent.md` with commits, files, red proof, six
mutation outputs, offline command output, live checks pending, cost/security
notes, and verdict. DeepSeek independently returns `APPROVED` or
`CHANGES_REQUESTED` with file:line evidence.
