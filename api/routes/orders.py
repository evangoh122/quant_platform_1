"""api/routes/orders.py — order intent + approval/cancel.

All writes go through the existing ``agent.tools_write`` contracts. The
approval path records a durable human-approval record (with the *authenticated*
principal as approver — never a client-supplied id) and then delegates to
``approve_and_place_paper_order(order_id)``, whose public signature accepts
only the order id so risk state can never be overridden by the caller.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel

from api.deps import AppUser, require_role
from api.schemas import OrderIntentRequest

router = APIRouter()


class OrderIntentResult(BaseModel):
    order_id: str
    status: str
    idempotency_key: str


class OrderActionResult(BaseModel):
    order_id: str
    status: str
    ok: bool
    broker_order_id: Optional[str] = None
    reason: Optional[str] = None
    risk: Optional[dict] = None


@router.post("/intents", response_model=OrderIntentResult, status_code=201)
def create_intent(
    body: OrderIntentRequest,
    user: AppUser = Depends(require_role("trader")),
) -> OrderIntentResult:
    try:
        from agent.tools_write import create_order_intent

        result = create_order_intent(
            symbol=body.symbol,
            side=body.side,
            quantity=body.quantity,
            order_type=body.order_type,
            limit_price=body.limit_price,
            signal_id=body.signal_id,
            idempotency_key=body.idempotency_key,
            user_id=user.user_id,
        )
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid order intent") from None
    except Exception:  # noqa: BLE001
        logger.exception("order intent write failed")
        raise HTTPException(status_code=503, detail="order write unavailable") from None
    return OrderIntentResult(
        order_id=result.get("order_id", ""),
        status=result.get("status", "PENDING_APPROVAL"),
        idempotency_key=result.get("idempotency_key", ""),
    )


@router.post("/{order_id}/approve", response_model=OrderActionResult)
def approve_order(
    order_id: str,
    user: AppUser = Depends(require_role("approver")),
) -> OrderActionResult:
    try:
        from agent.tools_write import (
            ApprovalContext,
            approve_and_place_paper_order,
            record_approval,
        )

        recorded = record_approval(order_id, ApprovalContext(approver_id=user.user_id))
        if not recorded.get("ok"):
            return OrderActionResult(
                order_id=order_id,
                status=recorded.get("status", "PENDING_APPROVAL"),
                ok=False,
                reason=recorded.get("reason"),
            )
        result = approve_and_place_paper_order(order_id)
    except Exception:  # noqa: BLE001
        logger.exception("order approval failed for %r", order_id)
        raise HTTPException(status_code=503, detail="approval unavailable") from None
    return OrderActionResult(
        order_id=result.get("order_id", order_id),
        status=result.get("status", ""),
        ok=bool(result.get("ok")),
        broker_order_id=result.get("broker_order_id"),
        reason=result.get("reason"),
        risk=result.get("risk"),
    )


@router.post("/{order_id}/cancel", response_model=OrderActionResult)
def cancel_order(
    order_id: str,
    user: AppUser = Depends(require_role("trader")),
) -> OrderActionResult:
    try:
        from agent.tools_write import cancel_paper_order

        result = cancel_paper_order(order_id, user.user_id)
    except Exception:  # noqa: BLE001
        logger.exception("order cancel failed for %r", order_id)
        raise HTTPException(status_code=503, detail="cancel unavailable") from None
    return OrderActionResult(
        order_id=result.get("order_id", order_id),
        status=result.get("status", ""),
        ok=bool(result.get("ok")),
        broker_order_id=result.get("broker_order_id"),
        reason=result.get("reason"),
    )
