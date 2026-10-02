"""api/routes/market.py — GET /api/market/{symbol}.

OHLCV features (``gold_ohlcv_features``) and options features
(``gold_options_features``) for a symbol. Reads go through the existing
``agent.tools_retrieval`` contracts (which normalize the symbol and enforce
PIT/freshness), never through string-built SQL.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from api.deps import AppUser, get_current_user, read_delta
from api.schemas import (
    Envelope,
    Freshness,
    MarketSnapshot,
    OHLCVFeature,
    OptionsFeature,
    iso,
)

router = APIRouter()


@router.get("/{symbol}", response_model=MarketSnapshot)
def market_features(
    symbol: str = Path(..., min_length=1, max_length=10),
    start_time: str = Query(default="1970-01-01T00:00:00Z"),
    end_time: str = Query(default="2999-01-01T00:00:00Z"),
    _user: AppUser = Depends(get_current_user),
) -> MarketSnapshot:
    from agent.guardrails import normalize_symbol

    try:
        symbol = normalize_symbol(symbol)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid symbol") from None

    def _read_ohlcv() -> list[dict]:
        from agent.tools_retrieval import get_market_features

        return get_market_features(symbol, start_time, end_time)

    def _read_options() -> list[dict]:
        from agent.tools_retrieval import get_options_features

        return get_options_features(symbol)

    ohlcv_rows, ohlcv_state, ohlcv_detail = read_delta(_read_ohlcv)
    opt_rows, opt_state, opt_detail = read_delta(_read_options)

    ohlcv = Envelope(
        data=[
            OHLCVFeature(
                symbol=str(r.get("symbol", symbol)),
                feature_ts=iso(r.get("feature_ts")) or "",
                open=r.get("open"),
                high=r.get("high"),
                low=r.get("low"),
                close=r.get("close"),
                volume=r.get("volume"),
                vwap=r.get("vwap"),
            )
            for r in ohlcv_rows
        ],
        count=len(ohlcv_rows),
        empty=not ohlcv_rows,
        source="gold_ohlcv_features",
        freshness=Freshness(state=ohlcv_state, table="gold_ohlcv_features", detail=ohlcv_detail),
    )
    options = Envelope(
        data=[
            OptionsFeature(
                symbol=str(r.get("symbol", symbol)),
                feature_ts=iso(r.get("feature_ts")) or "",
                expiry=iso(r.get("expiry")) or "",
                atm_iv=r.get("atm_iv"),
                skew=r.get("skew"),
                put_call_ratio=r.get("put_call_ratio"),
                volume_anomaly=r.get("volume_anomaly"),
            )
            for r in opt_rows
        ],
        count=len(opt_rows),
        empty=not opt_rows,
        source="gold_options_features",
        freshness=Freshness(state=opt_state, table="gold_options_features", detail=opt_detail),
    )
    return MarketSnapshot(symbol=symbol, ohlcv=ohlcv, options=options)
