# BUILD: chat security round 2 (MiMo)

> **IMPLEMENT NOW.** No confirmation questions. Commit after each fix. NEVER delete or weaken
> existing tests, EXCEPT to replace a vacuous test with a real one; list each replacement.

DeepSeek (`.agents/deepseek/VERDICT-chat-security.md`, read it fully) found 4 blocking issues:

1. **Default fall-through runs a tool** (`api/services/langgraph_engine.py:~1658-1660`). Replace the
   if/else with an explicit registry dispatch. An unknown or unregistered tool name → reject, with no
   execution and an audit event. Grep the whole codebase for any other `else:` that executes a
   default tool, and fix those too.
   Test: an unknown name (e.g. `sql_exec`) never reaches `_execute_tool` (spy asserts 0 calls).
2. **The red-team suite must exercise the real boundary.**
   - Build a **fake LLM provider** (deterministic, offline) that DELIBERATELY follows any instruction
     in its context: it emits tool calls for writes, leaks the system prompt, outputs markdown-image
     exfiltration, and so on. Inject it into the chat/langgraph engine through the existing provider
     seam.
   - Drive tests through **`TestClient`** against the mounted router: `/api/agent/chat` and the
     confirm-write endpoint, in authenticated mode (header identity), plus a public-demo-mode check
     that the route is absent (404).
   - Rewrite or replace every vacuous case DeepSeek listed (RT-07, RT-09 ×2, RT-20, RT-34, RT-35,
     `TestDeploymentModes` stubs) so each one asserts an observable outcome.
   - **Behavioural baseline proof:** in a /tmp copy, turn the security layer into a no-op (the facade
     returns pass-through). At least the write-escalation, indirect-injection, exfiltration and
     prompt-leak tests must FAIL there. An import error does NOT count. Paste the output in the
     verdict.
3. **Prompt inversion** (`langgraph_engine.py:~1586`): restore "do NOT enumerate specific
   competitors". Add a test asserting the grounding instruction text.
4. **Tool-call cap lockout** (`agent_chat.py:~78`, `tool_registry.py:~162-190`):
   - the cap must be per request/turn: generate a `turn_id` per request and reset/expire the counts;
   - the counters must be bounded (TTL or LRU);
   - Test: 11 sequential requests that each make 1 read call all succeed. One request making 11 calls
     is capped at 10.

Run:
- `python3 -m pytest -q -p no:cacheprovider tests/security tests/api`;
- the full suite with `--ignore=tests/lakebase`.

LF line endings only. Don't touch `.agents/dispatch.sh`. Leave no scratch files. Write
`.agents/mimo/VERDICT-chat-security-round2.md`.
