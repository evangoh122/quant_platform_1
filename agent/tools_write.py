"""agent/tools_write.py — real Lakebase-backed write tools.

Every tool performs a real transactional write against the Lakebase Postgres.
Queries are parameterized (``%s`` placeholders only) — never f-string SQL.

The execution boundary is non-bypassable by construction. The agent-facing tool
surface accepts only order identities and the acting user; it never accepts
trusted risk state (``engine``, ``market_session_open``, ``human_approved``,
``approved_by``, ``bridge``, buying power, or paper-mode flags). Those are
acquired by the production entry point from the store / market clock / broker
bridge. Test injection lives only behind private ``_``-prefixed seams that the
tool surface does not expose.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from agent.guardrails import (
    ACCOUNT_NOT_FOUND,
    MISSING_APPROVAL,
    SIGNAL_NOT_FOUND,
    OrderContext,
    RiskEngine,
    RiskViolation,
    is_market_session_open,
)
from db.lakebase import Lakebase, get_lakebase
from execution.bridge import IBKRBridge

# Statuses from which a new placement is still allowed.
_PLACEABLE_ORDER_STATUSES = ("PENDING_APPROVAL", "APPROVED")

# Statuses that count as "open" for conflicting-order detection. Includes
# SUBMITTING / SUBMITTED / PARTIALLY_FILLED so a second order cannot be opened
# while one is already in flight or already at the broker.
_OPEN_ORDER_STATUSES = (
    "PENDING_APPROVAL",
    "APPROVED",
    "SUBMITTING",
    "SUBMITTED",
    "PARTIALLY_FILLED",
)

# Broker responses that indicate a submission actually reached the broker.
_BROKER_SUCCESS_STATUSES = ("SUBMITTED", "FILLED", "PARTIALLY_FILLED")

# Broker cancellation responses that indicate the cancel was accepted.
_BROKER_CANCEL_SUCCESS = ("CANCELLED", "CANCEL_REQUESTED")

# Terminal order states (no further placement/cancellation possible).
_TERMINAL_STATUSES = ("CANCELLED", "REJECTED", "FAILED", "FILLED")

# Sentinel user for audit rows that have no attributable user (e.g. NOT_FOUND).
_SYSTEM_USER = "system"


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4()}"


def _dec(value, scale: str = "0.00000001") -> Optional[Decimal]:
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal(scale))


def _ensure_user(cur, user_id: str) -> None:
    """Guarantee the referenced user row exists (idempotent upsert)."""
    cur.execute(
        """
        INSERT INTO users (user_id, display_name, role, created_at)
        VALUES (%s, %s, 'trader', now())
        ON CONFLICT (user_id) DO NOTHING
        """,
        (user_id, user_id),
    )


def _log_action(
    cur, user_id: str, tool_name: str, action_type: str, input_summary: str,
    output_summary: str, status: str,
) -> str:
    action_id = _id("action")
    cur.execute(
        """
        INSERT INTO agent_actions
            (action_id, user_id, tool_name, action_type, input_summary, output_summary, status, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, now())
        """,
        (action_id, user_id, tool_name, action_type, input_summary, output_summary, status),
    )
    return action_id


# ── watchlists ────────────────────────────────────────────────────────────────
def add_to_watchlist(symbol: str, user_id: str = "default", *, db: Optional[Lakebase] = None) -> dict:
    """INSERT into watchlists; idempotent per (user, symbol)."""
    db = db or get_lakebase()
    watchlist_id = _id("wl")
    with db.transaction() as conn:
        with conn.cursor() as cur:
            _ensure_user(cur, user_id)
            cur.execute(
                """
                INSERT INTO watchlists (watchlist_id, user_id, symbol, created_at)
                VALUES (%s, %s, %s, now())
                ON CONFLICT (user_id, symbol)
                DO UPDATE SET symbol = EXCLUDED.symbol
                RETURNING watchlist_id, symbol
                """,
                (watchlist_id, user_id, symbol),
            )
            row = cur.fetchone()
            _log_action(
                cur, user_id, "add_to_watchlist", "write",
                f"symbol={symbol}", f"watchlist_id={row[0]}", "success",
            )
    return {"watchlist_id": row[0], "symbol": row[1], "status": "added"}


# ── research notes ────────────────────────────────────────────────────────────
def save_research_note(
    symbol: str, note_text: str, signal_id: Optional[str] = None,
    user_id: str = "default", *, db: Optional[Lakebase] = None,
) -> dict:
    """INSERT into research_notes."""
    db = db or get_lakebase()
    note_id = _id("note")
    with db.transaction() as conn:
        with conn.cursor() as cur:
            _ensure_user(cur, user_id)
            cur.execute(
                """
                INSERT INTO research_notes
                    (note_id, user_id, symbol, signal_id, note_text, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, now(), now())
                RETURNING note_id, symbol
                """,
                (note_id, user_id, symbol, signal_id, note_text),
            )
            row = cur.fetchone()
            _log_action(
                cur, user_id, "save_research_note", "write",
                f"symbol={symbol}", f"note_id={row[0]}", "success",
            )
    return {"note_id": row[0], "symbol": row[1], "status": "saved"}


# ── order intents ─────────────────────────────────────────────────────────────
def create_order_intent(
    symbol: str, side: str, quantity: float, order_type: str = "MARKET",
    limit_price: Optional[float] = None, notional: Optional[float] = None,
    signal_id: Optional[str] = None, idempotency_key: Optional[str] = None,
    user_id: str = "default", *, db: Optional[Lakebase] = None,
) -> dict:
    """INSERT an order in PENDING_APPROVAL state. No broker call. Idempotent by key."""
    db = db or get_lakebase()
    side = side.upper()
    order_type = order_type.upper()

    if notional is None:
        if limit_price is not None and quantity is not None:
            notional = float(quantity) * float(limit_price)
        else:
            raise ValueError("notional is required for MARKET orders without limit_price")

    key = idempotency_key or _id("idem")
    order_id = _id("ord")

    with db.transaction() as conn:
        with conn.cursor() as cur:
            _ensure_user(cur, user_id)
            cur.execute(
                """
                INSERT INTO orders
                    (order_id, user_id, signal_id, symbol, broker, side, quantity, notional,
                     order_type, limit_price, status, idempotency_key, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (idempotency_key) DO NOTHING
                RETURNING order_id, status, idempotency_key
                """,
                (
                    order_id, user_id, signal_id, symbol, "PAPER", side,
                    _dec(quantity), _dec(notional, "0.01"),
                    order_type, _dec(limit_price), "PENDING_APPROVAL", key,
                ),
            )
            row = cur.fetchone()
            if row is None:
                # idempotent replay: return the existing order untouched.
                cur.execute(
                    """
                    SELECT order_id, status, idempotency_key FROM orders
                    WHERE idempotency_key = %s
                    """,
                    (key,),
                )
                row = cur.fetchone()
                _log_action(
                    cur, user_id, "create_order_intent", "write",
                    f"symbol={symbol}, side={side}, key={key}",
                    f"idempotent replay order_id={row[0]}", "success",
                )
            else:
                _log_action(
                    cur, user_id, "create_order_intent", "write",
                    f"symbol={symbol}, side={side}, key={key}",
                    f"order_id={row[0]}", "success",
                )

    return {"order_id": row[0], "status": row[1], "idempotency_key": row[2]}


# ── human approval (trusted record) ───────────────────────────────────────────
def record_approval(order_id: str, approver_id: str, *,
                    db: Optional[Lakebase] = None) -> dict:
    """Persist a durable human-approval record for a PENDING_APPROVAL order.

    Placement reads this record back; it does not trust a caller-supplied
    boolean. The ``approver_id`` must be the authenticated principal (threaded
    from the request context by the orchestrator), never an agent assertion.
    """
    db = db or get_lakebase()
    approval_id = _id("approval")

    with db.transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, status FROM orders WHERE order_id = %s FOR UPDATE",
                (order_id,),
            )
            row = cur.fetchone()
            if row is None:
                _ensure_user(cur, _SYSTEM_USER)
                _log_action(
                    cur, _SYSTEM_USER, "record_approval", "write",
                    f"order_id={order_id}", "NOT_FOUND", "not_found",
                )
                return {"order_id": order_id, "status": "NOT_FOUND", "ok": False}

            user_id, status = row
            if status not in _PLACEABLE_ORDER_STATUSES:
                _log_action(
                    cur, user_id, "record_approval", "write",
                    f"order_id={order_id}",
                    f"cannot approve order in state {status}", "rejected",
                )
                return {
                    "order_id": order_id, "status": status, "ok": False,
                    "reason": f"cannot approve order in state {status}",
                }

            _ensure_user(cur, approver_id)
            cur.execute(
                """
                INSERT INTO approvals (approval_id, order_id, approver_id, created_at)
                VALUES (%s, %s, %s, now())
                ON CONFLICT (order_id)
                DO UPDATE SET approver_id = EXCLUDED.approver_id, created_at = now()
                RETURNING approval_id, approver_id
                """,
                (approval_id, order_id, approver_id),
            )
            arow = cur.fetchone()
            cur.execute(
                """
                UPDATE orders SET status = 'APPROVED', approved_by = %s, approved_at = now()
                WHERE order_id = %s
                """,
                (approver_id, order_id),
            )
            _log_action(
                cur, user_id, "record_approval", "write",
                f"order_id={order_id}", f"approver_id={approver_id}", "success",
            )

    return {
        "order_id": order_id, "approval_id": arow[0],
        "approver_id": arow[1], "status": "APPROVED", "ok": True,
    }


# ── approval / placement ──────────────────────────────────────────────────────
def approve_and_place_paper_order(order_id: str, *, db: Optional[Lakebase] = None) -> dict:
    """Re-run risk checks against trusted state, require a recorded approval,
    then place via the broker bridge.

    This public signature intentionally exposes only the order identity. The
    risk engine, market session, account buying power, allow-list, approval
    record, and broker bridge are all acquired by this entry point, so the agent
    cannot override any of them.
    """
    db = db or get_lakebase()
    engine = RiskEngine(load_allowlist=True)
    bridge = IBKRBridge()
    market_session_open = is_market_session_open()
    return _approve_and_place_paper_order(
        order_id,
        db=db,
        bridge=bridge,
        engine=engine,
        market_session_open=market_session_open,
    )


def _approve_and_place_paper_order(
    order_id: str,
    *,
    db: Lakebase,
    bridge: IBKRBridge,
    engine: RiskEngine,
    market_session_open: bool,
    now: Optional[datetime] = None,
) -> dict:
    """Private seam: full placement logic with injectable dependencies for tests.

    The agent-facing tool surface never reaches this function directly.
    """
    # Phase 1 — validate against trusted state and commit submission intent.
    with db.transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT order_id, user_id, signal_id, broker, side, quantity, notional,
                       order_type, limit_price, status, idempotency_key, symbol, broker_order_id
                FROM orders WHERE order_id = %s FOR UPDATE
                """,
                (order_id,),
            )
            order = cur.fetchone()
            if order is None:
                _ensure_user(cur, _SYSTEM_USER)
                _log_action(
                    cur, _SYSTEM_USER, "approve_and_place_paper_order", "write",
                    f"order_id={order_id}", "NOT_FOUND", "not_found",
                )
                return {"order_id": order_id, "status": "NOT_FOUND", "ok": False}

            (
                oid, user_id, signal_id, broker, side, quantity, notional,
                order_type, limit_price, status, key, symbol, broker_order_id,
            ) = order

            # Idempotent replay: an already-placed order is returned untouched
            # and is never re-submitted to the broker.
            if status in _BROKER_SUCCESS_STATUSES:
                _log_action(
                    cur, user_id, "approve_and_place_paper_order", "write",
                    f"order_id={order_id}",
                    f"idempotent replay status={status}", "success",
                )
                return {
                    "order_id": order_id, "status": status, "ok": True,
                    "broker_order_id": broker_order_id, "replay": True,
                }

            if status not in _PLACEABLE_ORDER_STATUSES:
                _log_action(
                    cur, user_id, "approve_and_place_paper_order", "write",
                    f"order_id={order_id}",
                    f"cannot place order in state {status}", "rejected",
                )
                return {
                    "order_id": order_id, "status": status, "ok": False,
                    "reason": f"cannot place order in state {status}",
                }

            # Trusted human-approval record — read back, never accepted inline.
            cur.execute(
                "SELECT approver_id FROM approvals WHERE order_id = %s",
                (order_id,),
            )
            arow = cur.fetchone()
            if arow is None:
                _log_action(
                    cur, user_id, "approve_and_place_paper_order", "write",
                    f"order_id={order_id}", "missing approval record", "rejected",
                )
                return {
                    "order_id": order_id, "status": status, "ok": False,
                    "risk": {
                        "passed": False,
                        "violations": [{
                            "code": MISSING_APPROVAL,
                            "message": "A recorded human approval is required",
                            "detail": {},
                        }],
                    },
                }
            approved_by = arow[0]

            # Trusted account source for buying power. Missing account fails
            # closed rather than substituting a fabricated constant.
            cur.execute(
                "SELECT buying_power FROM accounts WHERE account_id = %s",
                (user_id,),
            )
            arow = cur.fetchone()
            if arow is None:
                _log_action(
                    cur, user_id, "approve_and_place_paper_order", "write",
                    f"order_id={order_id}", "account not found", "rejected",
                )
                return {
                    "order_id": order_id, "status": status, "ok": False,
                    "risk": {
                        "passed": False,
                        "violations": [{
                            "code": ACCOUNT_NOT_FOUND,
                            "message": "No trusted buying-power account for this user",
                            "detail": {"account_id": user_id},
                        }],
                    },
                }
            buying_power = float(arow[0])

            # Current position notional (signed cost basis) for this user+symbol.
            cur.execute(
                """
                SELECT COALESCE(SUM(quantity * avg_cost), 0)
                FROM positions WHERE account_id = %s AND symbol = %s
                """,
                (user_id, symbol),
            )
            position_notional = float(cur.fetchone()[0] or 0)

            # Open/conflicting orders.
            cur.execute(
                """
                SELECT order_id, symbol, side, status FROM orders
                WHERE user_id = %s AND status = ANY(%s) AND order_id <> %s
                """,
                (user_id, list(_OPEN_ORDER_STATUSES), order_id),
            )
            open_orders = [
                {"order_id": r[0], "symbol": r[1], "side": r[2], "status": r[3]}
                for r in cur.fetchall()
            ]

            # Idempotency-key consumption: has this key already been seen on a
            # *different* order that reached the broker?
            cur.execute(
                """
                SELECT 1 FROM orders
                WHERE idempotency_key = %s AND order_id <> %s
                  AND status = ANY(%s)
                LIMIT 1
                """,
                (key, order_id, list(_BROKER_SUCCESS_STATUSES)),
            )
            idempotency_key_seen = cur.fetchone() is not None

            # Stale-signal source. A signal_id that cannot be resolved is a
            # hard failure — never a silent skip.
            signal_prediction_ts = None
            signal_unresolvable = False
            if signal_id:
                cur.execute(
                    "SELECT prediction_ts FROM signals WHERE signal_id = %s",
                    (signal_id,),
                )
                srow = cur.fetchone()
                if srow is None:
                    signal_unresolvable = True
                else:
                    signal_prediction_ts = srow[0]

            # is_paper is derived from the stored broker, not asserted.
            is_paper = (broker or "").upper() == "PAPER"

            ctx = OrderContext(
                symbol=symbol,
                side=side,
                quantity=float(quantity),
                notional=float(notional),
                order_type=order_type,
                limit_price=float(limit_price) if limit_price is not None else None,
                signal_prediction_ts=signal_prediction_ts,
                current_position_notional=position_notional,
                buying_power=buying_power,
                open_orders=open_orders,
                idempotency_key=key,
                idempotency_key_seen=idempotency_key_seen,
                is_paper=is_paper,
                market_session_open=market_session_open,
                now=now,
            )
            result = engine.check(ctx)

            if signal_unresolvable:
                result.violations.append(
                    RiskViolation(
                        SIGNAL_NOT_FOUND,
                        f"signal_id {signal_id} could not be resolved",
                        {"signal_id": signal_id},
                    )
                )

            if result.blocked:
                cur.execute(
                    "UPDATE orders SET status = 'REJECTED' WHERE order_id = %s",
                    (order_id,),
                )
                _log_action(
                    cur, user_id, "approve_and_place_paper_order", "write",
                    f"order_id={order_id}",
                    f"rejected: {result.to_dict()['violations'][0]['code']}", "rejected",
                )
                return {
                    "order_id": order_id, "status": "REJECTED", "ok": False,
                    "risk": result.to_dict(),
                }

            # Commit intent before any broker I/O.
            cur.execute(
                "UPDATE orders SET status = 'SUBMITTING' WHERE order_id = %s",
                (order_id,),
            )
            _log_action(
                cur, user_id, "approve_and_place_paper_order", "write",
                f"order_id={order_id}", "submission intent committed", "in_progress",
            )

    # Phase 2 — broker call, outside any open transaction.
    submit = bridge.submit_order(
        symbol=symbol, side=side, quantity=float(quantity),
        order_type="MKT" if order_type == "MARKET" else "LMT",
        limit_price=float(limit_price) if limit_price is not None else None,
    )
    broker_order_id = submit.get("broker_order_id")
    ok = submit.get("status") in _BROKER_SUCCESS_STATUSES
    new_status = "SUBMITTED" if ok else "FAILED"

    # Phase 3 — record the real outcome.
    with db.transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE orders
                SET status = %s, broker_order_id = %s, approved_by = %s,
                    approved_at = now(), submitted_at = now()
                WHERE order_id = %s
                """,
                (new_status, broker_order_id, approved_by, order_id),
            )
            _log_action(
                cur, user_id, "approve_and_place_paper_order", "write",
                f"order_id={order_id}",
                f"broker_order_id={broker_order_id}", "success" if ok else "failed",
            )

    return {
        "order_id": order_id, "status": new_status, "ok": ok,
        "broker_order_id": broker_order_id,
    }


# ── cancellation ──────────────────────────────────────────────────────────────
def cancel_paper_order(order_id: str, user_id: str = "default", *,
                       db: Optional[Lakebase] = None) -> dict:
    """Request cancellation via the broker bridge and update order state.

    Only the order identity and acting user are accepted; the bridge is acquired
    internally.
    """
    db = db or get_lakebase()
    bridge = IBKRBridge()
    return _cancel_paper_order(order_id, user_id, db=db, bridge=bridge)


def _cancel_paper_order(order_id: str, user_id: str, *, db: Lakebase,
                        bridge: IBKRBridge) -> dict:
    """Private seam for cancellation with injectable bridge."""
    with db.transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT broker_order_id, status FROM orders WHERE order_id = %s FOR UPDATE",
                (order_id,),
            )
            row = cur.fetchone()
            if row is None:
                _ensure_user(cur, _SYSTEM_USER)
                _log_action(
                    cur, _SYSTEM_USER, "cancel_paper_order", "write",
                    f"order_id={order_id}", "NOT_FOUND", "not_found",
                )
                return {"order_id": order_id, "status": "NOT_FOUND", "ok": False}

            broker_order_id, status = row
            if status in _TERMINAL_STATUSES:
                _ensure_user(cur, user_id)
                _log_action(
                    cur, user_id, "cancel_paper_order", "write",
                    f"order_id={order_id}",
                    f"cannot cancel order in terminal state {status}", "rejected",
                )
                return {
                    "order_id": order_id, "status": status, "ok": False,
                    "reason": f"cannot cancel order in terminal state {status}",
                }

            needs_broker = broker_order_id is not None
            # Only never-submitted intents may be cancelled locally.
            if not needs_broker and status not in ("PENDING_APPROVAL", "APPROVED"):
                _ensure_user(cur, user_id)
                _log_action(
                    cur, user_id, "cancel_paper_order", "write",
                    f"order_id={order_id}",
                    f"cannot cancel {status} order without a broker order id", "rejected",
                )
                return {
                    "order_id": order_id, "status": status, "ok": False,
                    "reason": f"cannot cancel {status} order without a broker order id",
                }

    # Phase 2 — broker cancel, outside any open transaction.
    cancel_ok = True
    if needs_broker:
        resp = bridge.cancel_order(broker_order_id)
        cancel_ok = resp.get("status") in _BROKER_CANCEL_SUCCESS

    new_status = "CANCELLED" if cancel_ok else "FAILED"

    # Phase 3 — record the real outcome.
    with db.transaction() as conn:
        with conn.cursor() as cur:
            _ensure_user(cur, user_id)
            cur.execute(
                "UPDATE orders SET status = %s WHERE order_id = %s",
                (new_status, order_id),
            )
            _log_action(
                cur, user_id, "cancel_paper_order", "write",
                f"order_id={order_id}", f"status={new_status}",
                "success" if cancel_ok else "failed",
            )

    return {"order_id": order_id, "status": new_status, "ok": cancel_ok}


# ── audit trail ───────────────────────────────────────────────────────────────
def record_agent_action(
    tool_name: str, action_type: str, input_summary: str, output_summary: str,
    status: str = "success", user_id: str = "default", *, db: Optional[Lakebase] = None,
) -> dict:
    """INSERT into agent_actions (standalone audit tool)."""
    db = db or get_lakebase()
    with db.transaction() as conn:
        with conn.cursor() as cur:
            _ensure_user(cur, user_id)
            action_id = _log_action(
                cur, user_id, tool_name, action_type, input_summary, output_summary, status,
            )
    return {"action_id": action_id, "tool_name": tool_name, "status": status}
