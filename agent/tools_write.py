"""agent/tools_write.py — real Lakebase-backed write tools.

Every tool performs a real transactional write against the Lakebase Postgres.
Queries are parameterized (``%s`` placeholders only) — never f-string SQL.

The agent-facing / trusted-internal separation is *advisory within this
process*, not an enforcement boundary. What is actually true today:

* The public placement entry point ``approve_and_place_paper_order(order_id)``
  accepts only an order identity and acquires the database connection, risk
  engine, market clock, and broker bridge itself. It never accepts trusted risk
  state (``engine``, ``market_session_open``, ``human_approved``,
  ``approved_by``, ``bridge``, buying power, ``db``, or paper-mode flags).
* Approval authority is separated from existence. ``_ensure_user`` provisions
  previously-unseen identities with the non-approving ``'viewer'`` role; the
  ``'trader'`` role (the only value in ``_APPROVER_ROLES``) is granted only by
  the out-of-band admin CLI ``scripts/grant_approver.py`` — never by an agent
  tool. ``record_approval`` therefore rejects auto-provisioned identities and
  cross-user approvals, but it does not stop a same-process Python caller from
  reaching the private seam below.
* The ``_``-prefixed seams (``_approve_and_place_paper_order``,
  ``_cancel_paper_order``) exist for test injection and are **not** an
  enforcement boundary: Python permits importing them directly, and ``__all__``
  governs only wildcard imports.

Boundaries intentionally NOT enforced here and tracked separately, pending the
authenticated API / agent-runtime layer (which does not exist in this repo yet):
*tool-surface isolation* — proving the agent-facing tool registry cannot reach
the private seams — and *approver authentication* — proving the caller really is
the ``approver_id`` they assert. A same-process Python caller that can import
this module and reach the private seams is **not** prevented by anything here.

Idempotency: ``orders.idempotency_key`` is ``UNIQUE``. That constraint is the
real duplicate guard; a repeated key is an idempotent replay handled by
``create_order_intent`` (``ON CONFLICT ... DO NOTHING`` + read-back), which
returns the existing order with ``reason == "DUPLICATE_IDEMPOTENCY_KEY"``. The
placement path therefore performs no redundant "seen" pre-check — such a check
is structurally unreachable under the unique constraint.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
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

# Public tool surface. Private ``_``-prefixed seams are deliberately excluded so
# ``from agent.tools_write import *`` can never surface the injectable internals.
__all__ = [
    "ApprovalContext",
    "PublicDemoWriteDisabled",
    "add_to_watchlist",
    "save_research_note",
    "create_order_intent",
    "record_approval",
    "approve_and_place_paper_order",
    "cancel_paper_order",
    "record_agent_action",
]


class PublicDemoWriteDisabled(RuntimeError):
    """Raised when a write tool is called in public-demo mode."""


def _reject_public_demo_write() -> None:
    """Reject write operations when public-demo mode is active.

    Must be called as the first executable statement in every write tool,
    before argument normalization, UUID generation, DB access, transactions,
    audit logging, market clock, risk engine, or broker acquisition.
    """
    from api.demo import is_public_demo

    if is_public_demo():
        raise PublicDemoWriteDisabled(
            "write operations are disabled in public demo mode"
        )

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

# users.role values permitted to record an approval. Only 'trader' is
# approver-authorized. 'trader' is NEVER granted by auto-provisioning
# (_ensure_user creates 'viewer') nor by any agent tool: it is granted solely
# out-of-band by scripts/grant_approver.py. Real approver authentication — who
# may approve which orders, for whom, from the authenticated principal — is the
# authenticated API layer's job and is pending (see module docstring).
_APPROVER_ROLES = ("trader",)


@dataclass(frozen=True)
class ApprovalContext:
    """Approval context carrying the caller-asserted approver identity.

    ``approver_id`` is the principal the caller asserts performed the approval;
    it is a plain string and nothing here authenticates it. ``record_approval``
    verifies the id is (1) an actual ``ApprovalContext``, (2) resolves to an
    existing ``users`` row whose role permits approval, and (3) is the order's
    owner. This rejects fabricated identities, auto-provisioned identities, and
    cross-user approvals. It cannot prove the caller *is* that principal —
    approver authentication belongs to the pending authenticated API layer.
    """

    approver_id: str


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4()}"


def _dec(value, scale: str = "0.00000001") -> Optional[Decimal]:
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal(scale))


def _ensure_user(cur, user_id: str) -> None:
    """Guarantee the referenced user row exists (idempotent upsert).

    New identities are provisioned with the non-approving ``'viewer'`` role.
    Approval authority (``'trader'``) is granted only out-of-band by
    ``scripts/grant_approver.py``; no agent tool may mint an approver.
    """
    cur.execute(
        """
        INSERT INTO users (user_id, display_name, role, created_at)
        VALUES (%s, %s, 'viewer', now())
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
    _reject_public_demo_write()
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
    user_id: str = "default", idempotency_key: Optional[str] = None,
    *, db: Optional[Lakebase] = None,
) -> dict:
    """INSERT into research_notes. Idempotent when idempotency_key is provided.

    A replay with the same idempotency_key returns the original note ID and
    does not create a second note or second effective analytics event.
    """
    _reject_public_demo_write()
    db = db or get_lakebase()
    note_id = _id("note")
    with db.transaction() as conn:
        with conn.cursor() as cur:
            _ensure_user(cur, user_id)
            if idempotency_key:
                cur.execute(
                    """
                    INSERT INTO research_notes
                        (note_id, user_id, symbol, signal_id, note_text,
                         idempotency_key, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, now(), now())
                    ON CONFLICT (idempotency_key) DO NOTHING
                    RETURNING note_id, symbol
                    """,
                    (note_id, user_id, symbol, signal_id, note_text, idempotency_key),
                )
                row = cur.fetchone()
                if row is None:
                    # Idempotent replay: read back the existing note.
                    cur.execute(
                        """
                        SELECT note_id, symbol FROM research_notes
                        WHERE idempotency_key = %s
                        """,
                        (idempotency_key,),
                    )
                    row = cur.fetchone()
                    _log_action(
                        cur, user_id, "save_research_note", "write",
                        f"symbol={symbol}, key={idempotency_key}",
                        f"idempotent replay note_id={row[0]}", "success",
                    )
                    return {
                        "note_id": row[0], "symbol": row[1],
                        "status": "saved", "replay": True,
                    }
            else:
                cur.execute(
                    """
                    INSERT INTO research_notes
                        (note_id, user_id, symbol, signal_id, note_text,
                         created_at, updated_at)
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
    _reject_public_demo_write()
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
            duplicate = row is None
            if duplicate:
                # Idempotent replay: the UNIQUE constraint on idempotency_key is
                # the real duplicate guard. Return the existing order untouched,
                # with a structured DUPLICATE_IDEMPOTENCY_KEY reason.
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

    result = {"order_id": row[0], "status": row[1], "idempotency_key": row[2]}
    if duplicate:
        result["reason"] = "DUPLICATE_IDEMPOTENCY_KEY"
        result["replay"] = True
    return result


# ── human approval (trusted record) ───────────────────────────────────────────
def record_approval(order_id: str, approver: ApprovalContext, *,
                    db: Optional[Lakebase] = None) -> dict:
    """Persist a durable human-approval record for a PENDING_APPROVAL order.

    Placement reads this record back; it does not trust a caller-supplied
    boolean. The ``approver`` must be an actual :class:`ApprovalContext`
    instance; anything else is rejected with ``INVALID_APPROVAL_CONTEXT``
    before any database work. Before writing anything, this verifies
    ``approver_id`` resolves to an existing ``users`` row whose role is in
    ``_APPROVER_ROLES`` (auto-provisioned identities are ``'viewer'`` and are
    therefore rejected with ``APPROVER_NOT_PERMITTED``), then verifies the
    approver is the order's owner (``APPROVER_NOT_OWNER``). An unknown,
    non-permitted, or non-owner approver is rejected with a structured reason
    and no approval row is written. This stops fabricated identities and
    cross-user approval, not a same-process caller (see module docstring).
    """
    _reject_public_demo_write()
    if not isinstance(approver, ApprovalContext):
        return {
            "order_id": order_id, "status": "REJECTED", "ok": False,
            "reason": "INVALID_APPROVAL_CONTEXT",
            "detail": {
                "expected": "ApprovalContext",
                "received": type(approver).__name__,
            },
        }
    db = db or get_lakebase()
    approver_id = approver.approver_id
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

            # Verify the approver is a real, permitted principal before writing
            # the approval. Auto-provisioned identities hold 'viewer' and are
            # rejected here; only the out-of-band 'trader' role may approve.
            # This does not stop a same-process caller (see module docstring).
            cur.execute(
                "SELECT role FROM users WHERE user_id = %s",
                (approver_id,),
            )
            urow = cur.fetchone()
            if urow is None:
                _log_action(
                    cur, user_id, "record_approval", "write",
                    f"order_id={order_id}", "unknown approver", "rejected",
                )
                return {
                    "order_id": order_id, "status": status, "ok": False,
                    "reason": "UNKNOWN_APPROVER",
                    "detail": {"approver_id": approver_id},
                }
            approver_role = urow[0]
            if approver_role not in _APPROVER_ROLES:
                _log_action(
                    cur, user_id, "record_approval", "write",
                    f"order_id={order_id}", "approver role not permitted", "rejected",
                )
                return {
                    "order_id": order_id, "status": status, "ok": False,
                    "reason": "APPROVER_NOT_PERMITTED",
                    "detail": {"approver_id": approver_id, "role": approver_role},
                }

            # Single-user paper-trading tool: "explicit human approval" means a
            # user confirming their own order. A granted approver may not approve
            # another user's order.
            if approver_id != user_id:
                _log_action(
                    cur, user_id, "record_approval", "write",
                    f"order_id={order_id}", "approver is not the order owner", "rejected",
                )
                return {
                    "order_id": order_id, "status": status, "ok": False,
                    "reason": "APPROVER_NOT_OWNER",
                    "detail": {"approver_id": approver_id, "owner_id": user_id},
                }

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
def approve_and_place_paper_order(order_id: str) -> dict:
    """Re-run risk checks against trusted state, require a recorded approval,
    then place via the broker bridge.

    The public signature exposes only the order identity. The database
    connection, risk engine, market session, account buying power, allow-list,
    approval record, and broker bridge are all acquired by this entry point
    rather than accepted as arguments, so the tool surface cannot pass them in.
    This is not an enforcement boundary against a same-process caller: the
    private test seam below remains importable (see module docstring).
    """
    _reject_public_demo_write()
    db = get_lakebase()
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
    """Test seam: full placement logic with injectable dependencies.

    Absent from ``__all__`` (which governs only ``import *``), and production
    code reaches this only through :func:`approve_and_place_paper_order`, which
    acquires every dependency itself. Tests inject fake stores / bridges /
    engines here. This seam is **not** an enforcement boundary: Python permits
    importing and calling it directly with injected ``db``/``bridge``/``engine``/
    ``market_session_open``/``now``. Isolating the agent-facing tool surface from
    it is the authenticated API layer's job and is pending.
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

            # Idempotency: orders.idempotency_key is UNIQUE — that constraint is
            # the real duplicate guard. A repeated key is an idempotent replay
            # handled by create_order_intent (which returns the existing order
            # with reason DUPLICATE_IDEMPOTENCY_KEY). No redundant "seen"
            # pre-check is performed here: under the unique constraint such a
            # check can never return true.

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
    _reject_public_demo_write()
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
    _reject_public_demo_write()
    db = db or get_lakebase()
    with db.transaction() as conn:
        with conn.cursor() as cur:
            _ensure_user(cur, user_id)
            action_id = _log_action(
                cur, user_id, tool_name, action_type, input_summary, output_summary, status,
            )
    return {"action_id": action_id, "tool_name": tool_name, "status": status}
