# VERDICT: lakebase-agent-tools — DeepSeek (Builder)

**Status:** APPROVED (builder self-verdict — independent Codex/Claude validation still required per PROTOCOL; a builder verdict is not the gate)
**Round:** 2
**Branch:** `slice/lakebase-agent-tools`; `main` untouched

Round-2 fix cycle. Every numbered item in `BUILD-lakebase-agent-tools-round2.md`
(1–17) is addressed below. No item is silently skipped. Two items (17) are
answered with an honest "unverified" statement rather than a fabricated number.

## Priority 1 — execution boundary (items 1–6)

1. **Public signatures no longer accept trusted state.**
   `approve_and_place_paper_order(order_id, *, db=None)` (`agent/tools_write.py:287`)
   exposes only the order identity. The production entry point acquires the risk
   engine (`RiskEngine(load_allowlist=True)`), the market session
   (`is_market_session_open()`), and the broker bridge (`IBKRBridge()`) itself.
   Test injection lives in the private seam `_approve_and_place_paper_order`
   (`agent/tools_write.py:309`), which the tool surface does not expose. A test
   proves the public signature cannot override risk state
   (`tests/lakebase/test_execution_boundary.py::test_public_signature_cannot_override_risk_state`
   via `inspect.signature`; also asserts `cancel_paper_order` has no `bridge`).

2. **Human approval is a durable record, not a boolean.**
   New `approvals` table (`db/migrations/002_approvals_accounts.sql`). New tool
   `record_approval(order_id, approver_id, *, db=None)`
   (`agent/tools_write.py:218`) persists the approval with an approver identity
   (idempotent `ON CONFLICT (order_id) DO UPDATE`). Placement reads the record
   back (`agent/tools_write.py:384`) and emits `MISSING_APPROVAL` if absent. The
   old `human_approved` / `approved_by` arguments are gone. Note: the
   `approver_id` on `record_approval` is the authenticated principal threaded
   from the request context by the orchestrator; this slice has no OIDC/auth
   framework to source it from, which is the honest remaining gap — but the
   caller can no longer assert "a human approved this" inline at placement.

3. **Three dead checks wired to real sources** (`agent/tools_write.py:395–472`):
   - `buying_power` → `SELECT buying_power FROM accounts WHERE account_id = %s`
     (new `accounts` table). Missing account fails closed with
     `ACCOUNT_NOT_FOUND`; `_DEFAULT_BUYING_POWER` constant removed.
   - `idempotency_key_seen` → real parameterized query against `orders`
     (`idempotency_key = %s AND order_id <> %s AND status = ANY(...)`).
   - `is_paper` → derived from the stored `broker` column
     (`(broker or "").upper() == "PAPER"`), no longer hardcoded `True`.

4. **`SUBMITTED` removed from placement eligibility.**
   `_PLACEABLE_ORDER_STATUSES = ("PENDING_APPROVAL", "APPROVED")`
   (`agent/tools_write.py:34`). `_OPEN_ORDER_STATUSES` still includes
   `SUBMITTING/SUBMITTED/PARTIALLY_FILLED` for *conflicting-order* detection, so
   re-approving a submitted order now returns an idempotent replay (no second
   broker call) instead of reaching `bridge.submit_order` again.

5. **Allow-list fails closed.** `load_allow_list()` (`agent/guardrails.py:112`)
   now raises on any load error instead of returning `None`. The production
   engine is always constructed `RiskEngine(load_allowlist=True)`, so a broken
   config propagates and rejects everything. Test:
   `tests/lakebase/test_guardrails.py::test_load_allow_list_fails_closed`.

6. **Stale-signal enforcement is not skippable.** An order whose `signal_id`
   cannot be resolved now emits `SIGNAL_NOT_FOUND` and is rejected
   (`agent/tools_write.py:459–500`) instead of silently skipping with
   `signal_prediction_ts=None`.

## Priority 2 — correctness and honesty (items 7–12)

7. **Real `ok` is returned and the real status is logged.** Phase 3 returns the
   computed `ok` and writes `_log_action(..., "success" if ok else "failed")`
   (`agent/tools_write.py:525–560`). A failed broker submission now returns
   `ok: False` and writes `status='failed'` to `agent_actions`.

8. **Broker call moved outside the open transaction.** Two-phase: Phase 1
   commits submission intent by setting `status='SUBMITTING'` (new status,
   `002_approvals_accounts.sql`) inside a transaction; Phase 2 calls the bridge
   with no open transaction; Phase 3 records the result in a new transaction
   (`agent/tools_write.py:517–560`). Retry on an already-placed order is
   idempotent via the replay branch at `agent/tools_write.py:347`. Documented
   residual gap: a crash in the `SUBMITTING` window (after intent commit, before
   the broker returns a `broker_order_id`) leaves an ambiguous state that the
   stub bridge cannot reconcile (no durable order-status query); this is a
   paper-bridge limitation, not a regression.

9. **Cancellation no longer fabricates success.** `_cancel_paper_order`
   (`agent/tools_write.py:574`) inspects the bridge response and only marks
   `CANCELLED` on an accepted status (`CANCELLED`/`CANCEL_REQUESTED`); a rejected
   cancel persists as `FAILED` with `ok: False`. Orders with no
   `broker_order_id` are cancelled locally only when still in
   `PENDING_APPROVAL`/`APPROVED`; a `SUBMITTING` order without a broker id is
   refused, not silently cancelled.

10. **Every tool call is audited.** The `NOT_FOUND` and terminal-state returns in
    approval and cancellation now write an `agent_actions` row (`status` of
    `not_found`/`rejected`/`success`/`failed` as appropriate) before returning.
    A `system` sentinel user is upserted for the un-attributable `NOT_FOUND` case.

11. **Two guardrail logic errors fixed.**
    - Duplicate/conflicting: `_check_duplicate` (`agent/guardrails.py:247`) now
      rejects on same symbol regardless of side, so an opposite-side open order
      is a conflict. Test: `test_opposite_side_open_order_is_conflict`.
    - Concentration: `_check_concentration` (`agent/guardrails.py:222`) applies a
      signed delta (SELL reduces exposure) and checks absolute exposure, so
      risk-reducing sells are no longer rejected. Tests:
      `test_sell_reduces_concentration`, `test_sell_that_overshoots_concentration_is_rejected`.

12. **Credential boundary sanitized.** `db/lakebase.py:67` now raises with only
    the exit code and request id — raw CLI stdout/stderr is never propagated.

## Priority 3 — tests prove the boundary (items 13–17)

13. **One no-broker-call test per risk check, offline.** New
    `tests/lakebase/test_execution_boundary.py` (not marked `lakebase`) drives the
    real `_approve_and_place_paper_order` path with a mocked bridge and asserts
    `submit_order.assert_not_called()` for: symbol, paper mode, quantity,
    notional, per-order notional, concentration, buying power, duplicate
    (opposite-side), market closed, stale signal, duplicate idempotency key,
    plus `SIGNAL_NOT_FOUND`, `ACCOUNT_NOT_FOUND`, `MISSING_APPROVAL`.

14. **Bypass not normalized in tests.** The old
    `test_approve_*` live tests that injected `engine`/`market_session_open` are
    removed. Live round-trips now go through the **public** signatures
    (`test_tools_write.py`); determinism is achieved by monkeypatching the clock
    (`tw.is_market_session_open`) and the bridge *construction site*
    (`tw.IBKRBridge`), never by passing trusted state as parameters.

15. **Migration test applies to an empty database.**
    `tests/lakebase/test_migrations.py::test_migrations_build_schema_from_scratch`
    creates a scratch schema, applies `001` + `002` from nothing, asserts all
    tables (`8 + approvals + accounts + schema_migrations`) exist, then drops the
    schema and resets `search_path`.

16. **Cancellation round-trip asserts the DB row and covers bridge failure.**
    `test_cancel_paper_order_roundtrip` (asserts `CANCELLED` row + bridge called
    with the broker id) and `test_cancel_paper_order_bridge_failure` (bridge
    returns `REJECTED` → row is `FAILED`, `ok: False`).

17. **Index/latency — honest statement.** Indexes exist and are used for PK /
    secondary-key lookups: `EXPLAIN` shows `Index Scan` for `positions_pkey`,
    `accounts_pkey`, and `idx_approvals_order`. For `orders`/`agent_actions` the
    planner currently chooses `Seq Scan` because those tables hold 0–1 rows
    (empty after each test run), so the cost model picks a full scan of an empty
    table. The `<500 ms` read / `<800 ms` write budgets are therefore
    **UNVERIFIED**: there is no production-scale data volume against which to
    measure p95. Stating this honestly rather than fabricating a number. The
    indexes (`idx_orders_user_status`, `orders_idempotency_key_key`,
    `idx_agent_actions_user_ts`, `idx_approvals_order`) are present and will be
    selected once `ANALYZE` statistics exist.

## Schema additions (kept 001 untouched)

`db/migrations/002_approvals_accounts.sql` adds `approvals` and `accounts`
tables, extends `orders.status` with `SUBMITTING`, and sets
`REPLICA IDENTITY FULL` on `approvals` (behavioural; `accounts` is config-like,
excluded like `users`). Forward-only and re-runnable. `001` was not modified.

## Checks run

```
$ python3 -m pytest tests/lakebase/ -q
67 passed in 73.62s
```

```
$ python3 -m pytest tests/lakebase/ -q -m "not lakebase"
51 passed, 16 deselected in 0.19s
```

```
$ grep -rnE 'f"' agent/ db/ | grep -iE 'select|insert|update|delete|where'
(no output — no f-string SQL)
```

```
$ git diff | grep -niE 'sk-[a-z0-9]{20,}|eyJ[a-z0-9_-]{20,}|password=|token='
(no output — no secrets)
```

## Gate

Per PROTOCOL, this is a builder verdict and is **not** the gate. Independent
validation by Codex and Claude is required. `main` is untouched; I have not
opened a PR.
