"""api/routes/analytics.py — GET /api/analytics.

Reads real aggregates from the four analytics Delta tables via the
Spark-or-SQL-warehouse adapter. Each section reports actual data, the exact
source table, row count, and freshness. When tables are empty or the backend
is unavailable, returns honest typed envelopes (never fabricated metrics).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends

from api.deps import AppUser, get_current_user, read_delta
from api.schemas import AnalyticsItem, AnalyticsResponse, Envelope, Freshness

router = APIRouter()

_SECTION_TABLE = {
    "model_performance": "analytics_model_performance",
    "agent_activity": "analytics_agent_activity",
    "latency": "analytics_latency",
    "stream_freshness": "analytics_stream_freshness",
    "watchlist_changes": "analytics_watchlist_changes",
    "order_funnel": "analytics_order_funnel",
    "usage_daily": "analytics_usage_daily",
}


def _read_section(section: str) -> List[Dict[str, Any]]:
    """Read rows from an analytics table via delta_adapter."""
    from db.delta_adapter import read_analytics_table

    return read_analytics_table(section, limit=500)


def _build_envelope(section: str) -> Envelope:
    """Build an Envelope for one analytics section with real data."""
    table = _SECTION_TABLE.get(section, f"analytics_{section}")

    def _fn() -> List[Dict[str, Any]]:
        return _read_section(section)

    rows, state, detail = read_delta(_fn)

    freshness = Freshness(state=state, table=table, detail=detail)
    return Envelope(
        data=rows,
        count=len(rows),
        empty=(len(rows) == 0),
        source=table,
        freshness=freshness,
    )


def _legacy_empty(table: str) -> Envelope[AnalyticsItem]:
    """Empty envelope for legacy sections not yet backed by analytics tables."""
    return Envelope(
        data=[],
        count=0,
        empty=True,
        source=table,
        freshness=Freshness(state="empty", table=table, detail="no analytics table"),
    )


@router.get("", response_model=AnalyticsResponse)
def analytics(_user: AppUser = Depends(get_current_user)) -> AnalyticsResponse:
    # New CDC-backed sections (real data or honest empty)
    watchlist_env = _build_envelope("watchlist_changes")
    funnel_env = _build_envelope("order_funnel")
    usage_env = _build_envelope("usage_daily")
    agent_env = _build_envelope("agent_activity")

    # Legacy sections — backed by tables that may not exist yet
    model_env = _build_envelope("model_performance")
    latency_env = _build_envelope("latency")
    stream_env = _build_envelope("stream_freshness")

    return AnalyticsResponse(
        model_performance=model_env,
        agent_activity=agent_env,
        latency=latency_env,
        stream_freshness=stream_env,
        watchlist_changes=watchlist_env,
        order_funnel=funnel_env,
        usage_daily=usage_env,
    )