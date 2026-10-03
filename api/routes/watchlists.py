"""api/routes/watchlists.py — GET /api/watchlists, POST /api/watchlists.

Reads the user's watchlist from Lakebase; writes go through the existing
``agent.tools_write.add_to_watchlist`` contract (idempotent per user+symbol).
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from api.deps import AppUser, get_current_user, require_role
from api.schemas import Envelope, Freshness, WatchlistItem, iso

router = APIRouter()


class WatchlistCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=10)


@router.get("", response_model=Envelope[WatchlistItem])
def list_watchlist(user: AppUser = Depends(get_current_user)) -> Envelope[WatchlistItem]:
    try:
        from agent.tools_retrieval import get_watchlist

        rows = get_watchlist(user.user_id)
        state = "fresh"
        detail = f"{len(rows)} rows"
    except Exception as exc:  # noqa: BLE001
        rows, state, detail = [], "unavailable", type(exc).__name__

    data = [WatchlistItem(symbol=r.get("symbol", ""), created_at=iso(r.get("created_at")) or "") for r in rows]
    return Envelope(
        data=data,
        count=len(data),
        empty=not data,
        source="watchlists",
        freshness=Freshness(state=state, table="watchlists", detail=detail),
    )


@router.post("", response_model=WatchlistItem, status_code=201)
def add_watchlist(
    body: WatchlistCreate,
    user: AppUser = Depends(require_role("trader")),
) -> WatchlistItem:
    try:
        from agent.tools_write import add_to_watchlist

        result = add_to_watchlist(body.symbol, user.user_id)
    except Exception:  # noqa: BLE001
        logger.exception("watchlist write failed")
        raise HTTPException(status_code=503, detail="watchlist write unavailable") from None
    return WatchlistItem(symbol=result.get("symbol", body.symbol))
