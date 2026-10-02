# BUILD-REQUEST: lakebase-agent-tools — ROUND 4 (final, small)

**Branch:** `slice/lakebase-agent-tools`
**Gate:** BLOCKED. Codex's final pass returned CHANGES_REQUESTED and overruled
my round-3 APPROVED. I checked and Codex is right.

**This round is small and mostly about honesty in the code's own claims.
Do not refactor working behaviour.**

Read `.agents/codex/VERDICT-...-round3-final.md` and
`.agents/claude/VERDICT-...-round3-corrected.md`.

## The finding

Round 3 claims the approval/execution boundary is non-bypassable. It is not:

- `ApprovalContext` is a public dataclass whose only field is
  `approver_id: str`, so `ApprovalContext(approver_id="fabricated")` constructs
  trivially and `record_approval` reads it without verifying provenance. It is
  the old bare-string trust model with a type around it.
- `__all__` exclusion does not make `_approve_and_place_paper_order`
  inaccessible — `from agent.tools_write import _approve_and_place_paper_order`
  still works, and that seam accepts an injected db, bridge, engine, market
  state and clock, reaching the only `bridge.submit_order` call.
- The boundary test asserts `__all__` membership, which proves nothing about
  reachability.

**Important context so you do not over-engineer:** no amount of code in this
slice makes this non-forgeable. A same-process Python caller can reach anything;
real enforcement needs an authenticated request context from the API layer,
which does not exist yet. **Do not invent an auth system, a fake registry, or a
signing scheme to satisfy this.**

## Do exactly these three things

### 1. Add the one real check that is achievable today

`record_approval` must verify `approver_id` exists in the `users` table (and is
permitted to approve) rather than trusting the string. This does not stop a
malicious in-process caller, but it does stop fabricated identities — a genuine
improvement available now. Return a structured reason on failure and make no
broker call.

Add a test: approval with an unknown `approver_id` is rejected, and
`submit_order.assert_not_called()`.

### 2. Stop overclaiming

The module docstring and `approve_and_place_paper_order`'s docstring assert the
boundary is non-bypassable while a note nearby defers the mechanism that would
make it so. That contradiction is the actual defect.

Rewrite those claims to state accurately:
- the public signature exposes only the order identity, and the entry point
  acquires trusted state itself;
- the private seam exists for tests and is **not** an enforcement boundary —
  Python does not prevent importing it;
- enforcement of tool-surface isolation and approver authentication belongs to
  the authenticated API layer and is **pending**, tracked separately.

Prefer precise and modest wording over reassuring wording.

### 3. Fix the boundary test's claim

`tests/lakebase/test_execution_boundary.py` should stop implying `__all__`
proves isolation. Either assert what is actually true (the public signature
rejects `db`/`engine`/`bridge`/`human_approved`/`market_session_open`, and the
public entry point acquires its own state), or rename the test so it does not
claim inaccessibility. Do not delete coverage.

## Do NOT do

- Do not weaken or revert anything from rounds 2-3. No regressions: the sole
  broker route must still validate risk first, call the broker outside the
  transaction, and record the real outcome.
- Do not touch the schema migrations.
- Do not change the latency module's honest "budgets unverified" statement. That
  was the right call and both validators accepted it.
- Do not touch: `conftest.py`, `pytest.ini`, `requirements*.txt`, `README.md`,
  `ml/`, `tests/ml/`, `silver/`, `gold/`, `api/`.

## Acceptance criteria

1. All three items done, or refused with a technical reason. Silence = not done.
2. `python3 -m pytest tests/lakebase/ -q` passes in full (currently `72 passed`)
   and offline (`53 passed`). Do not regress either. Paste real output for both.
3. `git diff --stat` is small.
4. **Commit your work.**
5. No new claim in the code that the slice cannot actually support.

## When finished

`.agents/deepseek/VERDICT-lakebase-agent-tools-round4.md`, per-item, with real
test output.
