"""api/schemas.py — API response contracts (pydantic v2).

These models are the single source of truth for the wire format; the frontend
types in ``frontend/src/api/types.ts`` mirror them. Every list endpoint returns
an :class:`Envelope` with an explicit freshness indicator so the UI can render
loading / empty / error states honestly — including when a backing table is
empty today (all ``gold_*`` / ``analytics_*`` tables are currently 0 rows) or
when a backend dependency (Delta / Lakebase) is unavailable.

This module is additive: it does not modify the read-only ``api/models``.
"""
from __future__ import annotations

from typing import Any, Dict, Generic, List, Literal, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

FreshnessState = Literal["fresh", "stale", "empty", "unavailable"]


def iso(value: Any) -> Optional[str]:
    """Coerce a datetime-like / scalar value to an ISO-8601 string (or None)."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


class Freshness(BaseModel):
    state: FreshnessState = "empty"
    table: str = ""
    detail: str = ""


class Envelope(BaseModel, Generic[T]):
    data: List[T] = Field(default_factory=list)
    count: int = 0
    empty: bool = True
    source: str = ""
    freshness: Freshness = Field(default_factory=Freshness)


# ── resources ─────────────────────────────────────────────────────────────────
class Signal(BaseModel):
    signal_id: str
    symbol: str
    direction: str = ""
    probability: Optional[float] = None
    prediction_ts: str = ""
    model_version: str = ""
    horizon: str = ""
    status: str = ""
    feature_snapshot_id: Optional[str] = None


class OHLCVFeature(BaseModel):
    symbol: str
    feature_ts: str = ""
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[float] = None
    vwap: Optional[float] = None


class OptionsFeature(BaseModel):
    symbol: str
    feature_ts: str = ""
    expiry: str = ""
    atm_iv: Optional[float] = None
    skew: Optional[float] = None
    put_call_ratio: Optional[float] = None
    volume_anomaly: Optional[float] = None


class MarketSnapshot(BaseModel):
    symbol: str
    ohlcv: Envelope[OHLCVFeature] = Field(default_factory=Envelope)
    options: Envelope[OptionsFeature] = Field(default_factory=Envelope)


class WatchlistItem(BaseModel):
    symbol: str
    created_at: str = ""


class Order(BaseModel):
    order_id: str
    symbol: str
    side: str = ""
    quantity: float = 0.0
    notional: float = 0.0
    order_type: str = ""
    limit_price: Optional[float] = None
    status: str = ""
    signal_id: Optional[str] = None
    idempotency_key: str = ""
    created_at: str = ""


class Position(BaseModel):
    account_id: str = ""
    symbol: str
    quantity: float = 0.0
    avg_cost: float = 0.0
    market_price: Optional[float] = None
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    updated_at: str = ""


class Portfolio(BaseModel):
    positions: Envelope[Position] = Field(default_factory=Envelope)
    orders: Envelope[Order] = Field(default_factory=Envelope)


# ── agent chat ────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ToolCall(BaseModel):
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    ok: bool = True


class ChatResponse(BaseModel):
    reply: str = ""
    tool_calls: List[ToolCall] = Field(default_factory=list)
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    available: bool = True
    empty: bool = True


# ── order intents ─────────────────────────────────────────────────────────────
class OrderIntentRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=10)
    side: Literal["BUY", "SELL"]
    quantity: float = Field(gt=0)
    order_type: Literal["MARKET", "LIMIT"] = "MARKET"
    limit_price: Optional[float] = None
    signal_id: Optional[str] = None
    idempotency_key: Optional[str] = None


# ── health / analytics ────────────────────────────────────────────────────────
class DependencyStatus(BaseModel):
    name: str
    ok: bool
    detail: str = ""


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str = ""
    dependencies: List[DependencyStatus] = Field(default_factory=list)
    freshness: Freshness = Field(default_factory=Freshness)


class AnalyticsItem(BaseModel):
    metric: str = ""
    value: Optional[float] = None
    detail: str = ""


class AnalyticsResponse(BaseModel):
    model_performance: Envelope[AnalyticsItem] = Field(default_factory=Envelope)
    agent_activity: Envelope[AnalyticsItem] = Field(default_factory=Envelope)
    latency: Envelope[AnalyticsItem] = Field(default_factory=Envelope)
    stream_freshness: Envelope[AnalyticsItem] = Field(default_factory=Envelope)
