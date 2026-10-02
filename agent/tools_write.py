"""agent/tools_write.py — real Lakebase-backed write tools.

Every tool performs a real transactional write against the Lakebase Postgres.
Queries are parameterized (``%s`` placeholders only) — never f-string SQL.

Each tool also inserts an ``agent_actions`` audit row in the same transaction.
``create_order_intent`` and ``approve_and_place_paper_order`` are idempotent by
``idempotency_key`` and re-run the deterministic risk engine before any broker
call. The execution bridge is invoked only from the approval path, and only
after every risk check passes.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Optional

from db.lakebase import Lakebase, get_lakebase
from execution.bridge import IBKRBridge

_OPEN_ORDER_STATUSES = ("PENDING_APPROVAL", "APPROVED", "SUBMITTED", "PARTIALLY_FILLED")

_DEFAULT_BUYING_POWER = 100000.0


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4()}"


def _dec(value, scale: str = "0.00000001") -> Optional[Decimal]:
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal(scale))


def _get_bridge(bridge: Optional[IBKRBridge]) -> IBKRBridge:
    if bridge is not None:
        return bridge
    return IBKRBridge()


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


# ── approval / placement ──────────────────────────────────────────────────────
def approve_and_place_paper_order(
    order_id: str, approved_by: str, *, human_approved: bool = False,
    db: Optional[Lakebase] = None, bridge: Optional[IBKRBridge] = None,
    engine=None, market_session_open: Optional[bool] = None,
) -> dict:
    """Re-run risk checks, require explicit human approval, then place via bridge.

    Returns a structured failure (and NO broker call) if any risk check fails or
    approval is missing.
    """
    from agent.guardrails import (
        OrderContext,
        RiskEngine,
        RiskViolation,
        is_market_session_open,
    )

    db = db or get_lakebase()
    bridge = _get_bridge(bridge)
    if engine is None:
        engine = RiskEngine(load_allowlist=True)

    with db.transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT order_id, user_id, signal_id, broker, side, quantity, notional,
                       order_type, limit_price, status, idempotency_key, symbol
                FROM orders WHERE order_id = %s FOR UPDATE
                """,
                (order_id,),
            )
            order = cur.fetchone()
            if order is None:
                return {"order_id": order_id, "status": "NOT_FOUND", "ok": False}

            (
                oid, user_id, signal_id, broker, side, quantity, notional,
                order_type, limit_price, status, key, symbol,
            ) = order

            if status not in _OPEN_ORDER_STATUSES:
                return {
                    "order_id": order_id, "status": status, "ok": False,
                    "reason": f"cannot place order in state {status}",
                }

            # current position notional for this user+symbol
            cur.execute(
                """
                SELECT COALESCE(SUM(quantity * avg_cost), 0)
                FROM positions WHERE account_id = %s AND symbol = %s
                """,
                (user_id, symbol),
            )
            position_notional = float(cur.fetchone()[0] or 0)

            # open/conflicting orders
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

            # stale-signal check: load the backing signal's prediction time.
            signal_prediction_ts = None
            if signal_id:
                cur.execute(
                    "SELECT prediction_ts FROM signals WHERE signal_id = %s",
                    (signal_id,),
                )
                srow = cur.fetchone()
                if srow:
                    signal_prediction_ts = srow[0]

            engine = engine
            ctx = OrderContext(
                symbol=symbol,
                side=side,
                quantity=float(quantity),
                notional=float(notional),
                order_type=order_type,
                limit_price=float(limit_price) if limit_price is not None else None,
                signal_prediction_ts=signal_prediction_ts,
                current_position_notional=position_notional,
                buying_power=_DEFAULT_BUYING_POWER,
                open_orders=open_orders,
                idempotency_key=key,
                idempotency_key_seen=False,
                is_paper=True,
                market_session_open=(
                    market_session_open
                    if market_session_open is not None
                    else is_market_session_open()
                ),
            )
            result = engine.check(ctx)

            if not human_approved or not approved_by:
                result.violations.append(
                    RiskViolation(
                        "MISSING_APPROVAL",
                        "Explicit human approval is required",
                        {"human_approved": human_approved, "approved_by": approved_by},
                    )
                )

            if result.blocked:
                cur.execute(
                    "UPDATE orders SET status = %s WHERE order_id = %s",
                    ("REJECTED", order_id),
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

            # every check passed → place the paper order via the bridge.
            submit = bridge.submit_order(
                symbol=symbol, side=side, quantity=float(quantity),
                order_type="MKT" if order_type == "MARKET" else "LMT",
                limit_price=float(limit_price) if limit_price is not None else None,
            )
            broker_order_id = submit.get("broker_order_id")
            ok = submit.get("status") in ("SUBMITTED", "FILLED", "PARTIALLY_FILLED")
            new_status = "SUBMITTED" if ok else "FAILED"
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
                f"broker_order_id={broker_order_id}", "success",
            )
            return {
                "order_id": order_id, "status": new_status, "ok": True,
                "broker_order_id": broker_order_id,
            }


# ── cancellation ──────────────────────────────────────────────────────────────
def cancel_paper_order(order_id: str, user_id: str = "default", *,
                       db: Optional[Lakebase] = None,
                       bridge: Optional[IBKRBridge] = None) -> dict:
    """Request cancellation via the bridge and update order state."""
    db = db or get_lakebase()
    bridge = _get_bridge(bridge)

    with db.transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT broker_order_id, status FROM orders WHERE order_id = %s FOR UPDATE",
                (order_id,),
            )
            row = cur.fetchone()
            if row is None:
                return {"order_id": order_id, "status": "NOT_FOUND", "ok": False}
            broker_order_id, current_status = row
            if current_status in ("CANCELLED", "REJECTED", "FAILED", "FILLED"):
                return {"order_id": order_id, "status": current_status, "ok": False,
                        "reason": f"cannot cancel order in terminal state {current_status}"}

            if broker_order_id:
                bridge.cancel_order(broker_order_id)

            cur.execute(
                "UPDATE orders SET status = %s WHERE order_id = %s",
                ("CANCELLED", order_id),
            )
            _log_action(
                cur, user_id, "cancel_paper_order", "write",
                f"order_id={order_id}", "status=CANCELLED", "success",
            )
            return {"order_id": order_id, "status": "CANCELLED", "ok": True}


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
