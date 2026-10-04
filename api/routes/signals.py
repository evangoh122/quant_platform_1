"""api/routes/signals.py — GET /api/signals.

Ranked signals from the ``gold_trading_signals`` Delta table. Returns a
well-formed empty envelope (with an explicit freshness indicator) when the table
is empty or Delta is unavailable — it never fabricates placeholder signals.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import AppUser, get_current_user, read_delta
from api.schemas import Envelope, Freshness, Signal, iso

router = APIRouter()


@router.get("", response_model=Envelope[Signal])
def list_signals(
    symbol: Optional[str] = Query(default=None, max_length=10),
    limit: int = Query(default=100, ge=1, le=1000),
    _user: AppUser = Depends(get_current_user),
) -> Envelope[Signal]:
    if symbol:
        try:
            from agent.guardrails import normalize_symbol

            symbol = normalize_symbol(symbol)
        except ValueError:
            raise HTTPException(status_code=422, detail="invalid symbol") from None

    def _read() -> list[dict]:
        from db.delta_adapter import latest_signals

        df = latest_signals(symbol, limit=limit)
        return [r.asDict() for r in df.collect()]

    from api.diagnostics import stage

    with stage("delta_read", table="gold_trading_signals", symbol=symbol or "all"):
        rows, state, detail = read_delta(_read)
    data = [
        Signal(
            signal_id=str(r.get("signal_id", "")),
            symbol=str(r.get("symbol", "")),
            direction=str(r.get("direction", "")),
            probability=r.get("probability"),
            prediction_ts=iso(r.get("prediction_ts")) or "",
            model_version=str(r.get("model_version", "")),
            horizon=str(r.get("horizon", "")),
            status=str(r.get("status", "")),
            feature_snapshot_id=r.get("feature_snapshot_id"),
        )
        for r in rows
    ]
    return Envelope(
        data=data,
        count=len(data),
        empty=not data,
        source="gold_trading_signals",
        freshness=Freshness(state=state, table="gold_trading_signals", detail=detail),
    )
