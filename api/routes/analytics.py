"""api/routes/analytics.py — GET /api/analytics.

Model performance, agent activity, latency, and stream freshness. The backing
analytics tables (``analytics_*``) are not yet populated, so every section
returns a well-formed empty envelope with an explicit ``empty`` freshness
indicator — it never fabricates metrics.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import AppUser, get_current_user
from api.schemas import AnalyticsItem, AnalyticsResponse, Envelope, Freshness

router = APIRouter()

_EMPTY_SECTIONS = {
    "model_performance": "analytics_model_performance",
    "agent_activity": "analytics_agent_activity",
    "latency": "analytics_latency",
    "stream_freshness": "analytics_stream_freshness",
}


def _empty_envelope(table: str) -> Envelope:
    return Envelope(
        data=[],
        count=0,
        empty=True,
        source=table,
        freshness=Freshness(state="empty", table=table, detail="0 rows"),
    )


@router.get("", response_model=AnalyticsResponse)
def analytics(_user: AppUser = Depends(get_current_user)) -> AnalyticsResponse:
    return AnalyticsResponse(
        model_performance=_empty_envelope(_EMPTY_SECTIONS["model_performance"]),
        agent_activity=_empty_envelope(_EMPTY_SECTIONS["agent_activity"]),
        latency=_empty_envelope(_EMPTY_SECTIONS["latency"]),
        stream_freshness=_empty_envelope(_EMPTY_SECTIONS["stream_freshness"]),
    )
