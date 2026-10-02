# BUILD-REQUEST: lakebase-agent-tools — ROUND 3 (narrow close-out)

**Branch:** `slice/lakebase-agent-tools` (continue)
**Gate:** BLOCKED on four items. **This is a small, surgical round — do not
rewrite anything that works.**

## Round 2 went well — read this before you touch anything

17 of 21 items are FIXED and I verified the important ones myself. The full
test suite **passes**: `67 passed` including all 16 live Lakebase tests
(Codex reported live failures, but that was its sandbox blocking the
`databricks` CLI — not a real defect; ignore that line of its report).

**Do not re-litigate or refactor the fixed work.** Only the four items below.

Full detail: `.agents/codex/VERDICT-lakebase-agent-tools-round2.md` and
`.agents/claude/VERDICT-lakebase-agent-tools-round2.md`.

---

## Item 1 — close the execution boundary as far as it closes today

Fixed already: `engine`, `human_approved`, `approved_by`, `bridge` and
`market_session_open` are gone from the public signature. Remaining gaps:

1. **`db` is still caller-injectable** on the public placement function. A
   caller supplying a fabricated `db` can fabricate orders, approvals, accounts
   and buying power. Remove it from the public signature; the public entry point
   acquires its own connection.
2. **`_approve_and_place_paper_order` is directly importable.** Keep a test
   seam, but make it genuinely private — not exported in `__all__`, and
   documented as test-only.
3. **`record_approval` takes a caller-supplied `approver_id`** with only a
   docstring saying it "must" be authenticated. Either derive it from an
   authenticated context, or — if no auth context exists in this slice yet —
   make the function *require* an explicit context object rather than a bare
   string, so a caller cannot pass `"someone"` and have it accepted as proof.
4. **Deepen `tests/lakebase/test_execution_boundary.py`.** It currently only
   inspects five parameter names. It must assert the public signature rejects
   `db` too, and that the private seam is not in the module's public exports.

**Explicitly out of scope — do not fake it.** Codex also asked for proof that
"the agent-facing tool surface cannot call the private function." There is **no
agent runtime or tool-registration layer in this repo yet**, so there is nothing
real to assert against. Do **not** invent a registry just to satisfy the check.
Instead add a short note in the module docstring stating that tool-surface
isolation must be enforced and tested when the agent runtime lands. I am
tracking it separately.

## Item 4 — resolve the idempotency redundancy

The `idempotency_key_seen` query is real SQL, but it **cannot return true**: the
unique constraint on `orders.idempotency_key` rejects the insert before the
check can fire. So one of the two is redundant.

Decide deliberately and state the reasoning in your verdict:
- If the constraint is the real guard, the check should catch the constraint
  violation and return the structured `DUPLICATE_IDEMPOTENCY_KEY` reason rather
  than letting a raw integrity error surface; **or**
- if the pre-check is the real guard, explain how it can ever fire.

Either way, add a test that drives the duplicate path end to end and asserts the
structured reason **and** that no broker call occurred.

## Item 16 — stop normalizing bypasses in tests

Some tests still inject the risk engine or market-session result, which is the
production hole itself. Convert them to drive the non-overridable public path.
Keep coverage equivalent — do not delete a test to satisfy this.

## Item 19 — index and latency evidence (NOT FIXED in two rounds)

This was requested twice and is still entirely absent: no `EXPLAIN`, no
percentile measurement.

Do **one** of these, honestly:
- **(a)** Add a test that runs `EXPLAIN` on each operational query and asserts an
  index scan rather than a sequential scan, plus a measured p50/p95 for the
  agent read and write tools against the live instance. Paste real numbers.
- **(b)** If (a) is impractical, write the measurement you *can* make and state
  plainly in the module docstring and your verdict that the <500 ms read /
  <800 ms write budgets are **unverified**, with the reason.

**A silent omission is a third failure of this item. An honest "unverified" is
acceptable; silence is not.**

---

## Acceptance criteria

1. All four items addressed or explicitly refused with a technical reason.
   Silence on an item counts as not done.
2. `python3 -m pytest tests/lakebase/ -q` still passes in full (it is at
   `67 passed` — do not regress it). Paste real output for both the offline
   (`-m "not lakebase"`) and full selections.
3. No rewrite of round-2 fixes. `git diff --stat` should be small.
4. **Commit your work before finishing.** Round 2 ended without committing and
   I had to commit on your behalf.
5. No secrets. `main` untouched.

## Do not touch

`conftest.py`, `pytest.ini`, `requirements*.txt`, `README.md` (F0 lane);
`ml/`, `tests/ml/` (ML lane); `silver/`, `gold/` (Silver/Gold lane);
`api/` (restructure lane). Do not change the schema migrations — they are correct.

## When finished

Write `.agents/deepseek/VERDICT-lakebase-agent-tools-round3.md` per
`.agents/PROTOCOL.md`, with a per-item FIXED / REFUSED line and real test output.
