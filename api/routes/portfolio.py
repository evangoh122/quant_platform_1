"""api/routes/portfolio.py — GET /api/portfolio.

Positions and open orders from Lakebase via the existing
``agent.tools_retrieval`` read contracts. Degrades to a well-formed empty
envelope when Lakebase is unreachable or has no rows yet.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import AppUser, get_current_user
from api.schemas import Envelope, Freshness, Order, Portfolio, Position, iso

router = APIRouter()


@router.get("", response_model=Portfolio)
def portfolio(user: AppUser = Depends(get_current_user)) -> Portfolio:
    try:
        from agent.tools_retrieval import get_open_orders, get_portfolio_positions

        positions = get_portfolio_positions(user.user_id)
        orders = get_open_orders(user.user_id)
        pos_state, pos_detail = ("fresh", f"{len(positions)} rows")
        ord_state, ord_detail = ("fresh", f"{len(orders)} rows")
    except Exception as exc:  # noqa: BLE001
        positions, orders = [], []
        pos_state = ord_state = "unavailable"
        pos_detail = ord_detail = type(exc).__name__

    position_env = Envelope(
        data=[
            Position(
                account_id=str(r.get("account_id", "")),
                symbol=str(r.get("symbol", "")),
                quantity=float(r.get("quantity") or 0),
                avg_cost=float(r.get("avg_cost") or 0),
                market_price=r.get("market_price"),
                realized_pnl=r.get("realized_pnl"),
                unrealized_pnl=r.get("unrealized_pnl"),
                updated_at=iso(r.get("updated_at")) or "",
            )
            for r in positions
        ],
        count=len(positions),
        empty=not positions,
        source="positions",
        freshness=Freshness(state=pos_state, table="positions", detail=pos_detail),
    )
    order_env = Envelope(
        data=[
            Order(
                order_id=str(r.get("order_id", "")),
                symbol=str(r.get("symbol", "")),
                side=str(r.get("side", "")),
                quantity=float(r.get("quantity") or 0),
                notional=float(r.get("notional") or 0),
                order_type=str(r.get("order_type", "")),
                limit_price=r.get("limit_price"),
                status=str(r.get("status", "")),
                signal_id=r.get("signal_id"),
                idempotency_key=str(r.get("idempotency_key", "")),
                created_at=iso(r.get("created_at")) or "",
            )
            for r in orders
        ],
        count=len(orders),
        empty=not orders,
        source="orders",
        freshness=Freshness(state=ord_state, table="orders", detail=ord_detail),
    )
    return Portfolio(positions=position_env, orders=order_env)
