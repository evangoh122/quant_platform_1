# BUILD-REQUEST: lakebase-agent-tools — ROUND 2 (fix cycle)

**Branch:** `slice/lakebase-agent-tools` (continue on it)
**Gate status:** **BLOCKED.** Round 1 was self-approved by you but rejected by
two independent validators. Do not self-approve again.

## Read these first

- `.agents/codex/VERDICT-lakebase-agent-tools.md` — 20 blocking findings, each
  with `file:line`.
- `.agents/claude/VERDICT-lakebase-agent-tools.md` — architecture verdict plus
  one finding Codex missed.

Both verdicts were independently source-verified. The findings are real — I
confirmed the five most severe myself by reading your code. Do not argue them;
fix them.

## What you got right — keep it

The live schema is correct (8 tables, 19 indexes, 5 CHECK constraints,
`REPLICA IDENTITY FULL` on exactly the 7 behavioural tables). The SQL-injection
fixes are genuine. No secrets committed. The write tools do real I/O. The CDC
publication finding was good work. **Do not rewrite these.**

## Priority 1 — the execution boundary must become non-bypassable

The core defect: your risk service is a pure function whose trusted inputs are
supplied by the caller. An agent that can call the tool can defeat every check.

1. **Stop accepting trusted state as public parameters.**
   `approve_and_place_paper_order` must not take `engine`, `human_approved`,
   `approved_by`, `market_session_open`, or `bridge` from its caller. The
   production entry point acquires these itself. If you need injection for
   tests, put it behind a separate private/internal seam that the agent-facing
   tool surface does not expose — and add a test proving the public signature
   cannot override risk state.

2. **Human approval must be a trusted record, not an argument.** Persist an
   approval with an authenticated approver identity and read it back; a boolean
   parameter asserting "a human approved this" is not approval.

3. **Wire the three dead checks to real sources:**
   - `buying_power` — from a trusted account source, not `_DEFAULT_BUYING_POWER`.
   - `idempotency_key_seen` — query `orders` for the key; it is currently
     hardcoded `False`, so `DUPLICATE_IDEMPOTENCY_KEY` can never fire.
   - `is_paper` — derive from the stored `broker`/account you already load at
     line 227; it is currently hardcoded `True`.

4. **Remove `SUBMITTED` from `_OPEN_ORDER_STATUSES`** (line 21) for placement
   eligibility. Today, re-approving a submitted order reaches
   `bridge.submit_order` again and can place a duplicate broker order.

5. **Allow-list must fail CLOSED.** `agent/guardrails.py:110` returns `None` on
   any load error, after which only ticker *syntax* is checked. A config error
   must reject everything, not admit everything.

6. **Stale-signal enforcement must not be skippable.** A `signal_id` that fails
   to load leaves `signal_prediction_ts=None` and the check is bypassed. Either
   reject the order or treat an unresolvable signal as stale.

## Priority 2 — correctness and honesty of results

7. **`ok` is computed then discarded.** At line 342 you return the literal
   `"ok": True` regardless of the broker outcome, and `_log_action(..., "success")`
   fires on the same path. A failed submission therefore reports success **and
   writes a `status='success'` audit row**. `agent_actions` is the declared
   source for `analytics_agent_activity`, so this poisons the downstream
   analytics slice. Return the real outcome and log the real status.

8. **Move the broker call outside the open transaction.** A successful broker
   submission followed by a commit failure rolls back the DB while the external
   order is live, and a retry can duplicate it. Commit intent first, then call
   the broker, then record the result — and make the retry path idempotent.

9. **Cancellation must not fabricate success.** Orders with no
   `broker_order_id` are marked `CANCELLED` with no bridge I/O, and bridge
   responses are ignored — even a rejected cancellation persists as cancelled.

10. **Audit every tool call, as claimed.** The `NOT_FOUND` and invalid/terminal
    state early-returns in approval and cancellation exit without writing
    `agent_actions`.

11. **Fix the two guardrail logic errors.** Conflicting open orders: only
    same-symbol/same-side is rejected, so an opposite-side open order passes.
    Concentration: order notional is always *added*, including for SELL, which
    can reject risk-reducing sells.

12. **Sanitize the credential boundary.** `db/lakebase.py:65` copies raw CLI
    stderr/stdout into an exception that can propagate to agent-visible output.

## Priority 3 — tests must prove the boundary, not mock it

Your tests pass but do not establish the claims. This is the part to take most
seriously.

13. **One no-broker-call test per risk check.** For each of the ten checks,
    drive the **real execution path** with a mocked bridge and assert
    `submit_order.assert_not_called()`. Today only one aggregated case does
    this, and it is marked `lakebase`, so it is excluded from the offline
    command you reported as proof.

14. **Do not normalize the bypass in tests.** `test_tools_write.py:83` injects
    the engine and market-session result, which is precisely the production
    hole. Tests must exercise the non-overridable path.

15. **Migration test must apply to an empty database.** Currently the fixture
    migrates the shared schema first, then asserts a second run returns `[]`.
    That tests idempotency only, not that the migration builds a schema from
    nothing. Use a scratch schema/database.

16. **Cancellation round-trip** must assert the DB row afterwards and cover
    bridge failure.

17. **Index/latency proof is absent.** Provide `EXPLAIN` evidence that
    operational queries use indexes, and real p95 numbers for the stated
    <500 ms read / <800 ms write budgets — or state honestly that the budget is
    unverified and why.

## Acceptance criteria for round 2

1. Every numbered item above is addressed, or explicitly refused in your verdict
   with a technical reason. Silence on an item counts as not done.
2. `python3 -m pytest tests/lakebase/ -q` passes, **and** the no-broker-call
   tests run in the offline (`-m "not lakebase"`) selection. Paste real output.
3. A test exists proving the public tool signature cannot override risk state.
4. No secrets. `main` untouched.

## Do not touch

`conftest.py` — a concurrent lane owns it. `ml/`, `pipelines/` — other lanes.
Do not revert or rewrite the schema migration; it is correct.
