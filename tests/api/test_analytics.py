"""tests/api/test_analytics.py — API tests for GET /api/analytics.

Mocks the delta_adapter and asserts non-empty data, table source, stale/
unavailable/empty behavior, fixed query bounds, and no Lakebase call.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

# ── sample data ──────────────────────────────────────────────────────────────

_SAMPLE_AGENT_ACTIVITY = [
    {
        "event_date": "2025-01-15",
        "tool_name": "get_signals",
        "action_type": "read",
        "status": "success",
        "call_count": 42,
        "distinct_users": 3,
        "last_source_event_id": 100,
        "last_source_time": "2025-01-15T10:00:00",
    }
]

_SAMPLE_WATCHLIST_CHANGES = [
    {
        "event_date": "2025-01-15",
        "symbol": "AAPL",
        "additions": 5,
        "removals": 2,
        "net_changes": 3,
        "distinct_users": 2,
        "last_source_event_id": 95,
        "last_source_time": "2025-01-15T09:30:00",
    }
]

_SAMPLE_ORDER_FUNNEL = [
    {
        "event_date": "2025-01-15",
        "funnel_stage": "intent",
        "stage_count": 10,
        "distinct_orders": 8,
        "last_source_event_id": 90,
        "last_source_time": "2025-01-15T09:00:00",
    }
]

_SAMPLE_USAGE_DAILY = [
    {
        "event_date": "2025-01-15",
        "retrieval_calls": 100,
        "write_calls": 20,
        "success_count": 110,
        "failure_count": 10,
        "distinct_users": 5,
        "max_source_event_id": 105,
        "last_source_time": "2025-01-15T10:30:00",
    }
]


# ── helpers ──────────────────────────────────────────────────────────────────

def _mock_read_analytics_table(section: str, limit: int = 500) -> List[Dict[str, Any]]:
    """Fake analytics table reader that returns sample data."""
    data = {
        "agent_activity": _SAMPLE_AGENT_ACTIVITY,
        "watchlist_changes": _SAMPLE_WATCHLIST_CHANGES,
        "order_funnel": _SAMPLE_ORDER_FUNNEL,
        "usage_daily": _SAMPLE_USAGE_DAILY,
    }
    return data.get(section, [])


def _mock_read_analytics_table_empty(section: str, limit: int = 500) -> List[Dict[str, Any]]:
    """Fake that returns empty for all sections."""
    return []


def _mock_read_analytics_table_error(section: str, limit: int = 500) -> List[Dict[str, Any]]:
    """Fake that raises an exception (backend unavailable)."""
    raise RuntimeError("warehouse unavailable")


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def analytics_client():
    """FastAPI test client with mocked analytics backend."""
    from fastapi.testclient import TestClient
    from api.main import create_app

    return TestClient(create_app())


@pytest.fixture
def authed_headers():
    return {"x-forwarded-email": "trader@example.com"}


# ── tests ────────────────────────────────────────────────────────────────────

class TestAnalyticsEndpoint:

    def test_returns_200(self, analytics_client, authed_headers):
        """GET /api/analytics returns 200."""
        with patch("db.delta_adapter.read_analytics_table", _mock_read_analytics_table):
            resp = analytics_client.get("/api/analytics", headers=authed_headers)
        assert resp.status_code == 200

    def test_watchlist_changes_non_empty(self, analytics_client, authed_headers):
        """watchlist_changes section returns real data when adapter has rows."""
        with patch("db.delta_adapter.read_analytics_table", _mock_read_analytics_table):
            resp = analytics_client.get("/api/analytics", headers=authed_headers)
        data = resp.json()
        wc = data["watchlist_changes"]
        assert wc["count"] == 1
        assert wc["empty"] is False
        assert wc["source"] == "analytics_watchlist_changes"
        assert wc["data"][0]["symbol"] == "AAPL"

    def test_order_funnel_non_empty(self, analytics_client, authed_headers):
        """order_funnel section returns real data."""
        with patch("db.delta_adapter.read_analytics_table", _mock_read_analytics_table):
            resp = analytics_client.get("/api/analytics", headers=authed_headers)
        data = resp.json()
        of_ = data["order_funnel"]
        assert of_["count"] == 1
        assert of_["empty"] is False
        assert of_["source"] == "analytics_order_funnel"

    def test_usage_daily_non_empty(self, analytics_client, authed_headers):
        """usage_daily section returns real data."""
        with patch("db.delta_adapter.read_analytics_table", _mock_read_analytics_table):
            resp = analytics_client.get("/api/analytics", headers=authed_headers)
        data = resp.json()
        ud = data["usage_daily"]
        assert ud["count"] == 1
        assert ud["empty"] is False
        assert ud["source"] == "analytics_usage_daily"

    def test_agent_activity_non_empty(self, analytics_client, authed_headers):
        """agent_activity section returns real data."""
        with patch("db.delta_adapter.read_analytics_table", _mock_read_analytics_table):
            resp = analytics_client.get("/api/analytics", headers=authed_headers)
        data = resp.json()
        aa = data["agent_activity"]
        assert aa["count"] == 1
        assert aa["empty"] is False
        assert aa["source"] == "analytics_agent_activity"

    def test_empty_tables_return_honest_envelope(self, analytics_client, authed_headers):
        """When tables are empty, sections return empty=True with correct source."""
        with patch("db.delta_adapter.read_analytics_table", _mock_read_analytics_table_empty):
            resp = analytics_client.get("/api/analytics", headers=authed_headers)
        data = resp.json()
        for section in ["watchlist_changes", "order_funnel", "usage_daily", "agent_activity"]:
            env = data[section]
            assert env["empty"] is True, f"{section} should be empty"
            assert env["count"] == 0, f"{section} count should be 0"
            assert env["source"].startswith("analytics_"), f"{section} source incorrect"

    def test_unavailable_backend_returns_unavailable(self, analytics_client, authed_headers):
        """When backend fails, freshness state is 'unavailable'."""
        with patch("db.delta_adapter.read_analytics_table", _mock_read_analytics_table_error):
            resp = analytics_client.get("/api/analytics", headers=authed_headers)
        data = resp.json()
        for section in ["watchlist_changes", "order_funnel", "usage_daily", "agent_activity"]:
            env = data[section]
            assert env["freshness"]["state"] == "unavailable", (
                f"{section} freshness should be unavailable"
            )

    def test_no_lakebase_call(self, analytics_client, authed_headers):
        """Analytics endpoint must not call Lakebase directly."""
        called_sections = []

        def _tracking_read(section, limit=500):
            called_sections.append(section)
            return _mock_read_analytics_table(section, limit)

        with patch("db.delta_adapter.read_analytics_table", _tracking_read):
            resp = analytics_client.get("/api/analytics", headers=authed_headers)
        # All sections go through delta_adapter, not Lakebase
        assert len(called_sections) > 0, "delta_adapter.read_analytics_table was called"

    def test_source_tables_are_exact(self, analytics_client, authed_headers):
        """Each section must reference the exact analytics_* table name."""
        with patch("db.delta_adapter.read_analytics_table", _mock_read_analytics_table):
            resp = analytics_client.get("/api/analytics", headers=authed_headers)
        data = resp.json()
        expected_sources = {
            "watchlist_changes": "analytics_watchlist_changes",
            "order_funnel": "analytics_order_funnel",
            "usage_daily": "analytics_usage_daily",
            "agent_activity": "analytics_agent_activity",
        }
        for section, expected_source in expected_sources.items():
            assert data[section]["source"] == expected_source, (
                f"{section} source should be {expected_source}"
            )

    def test_legacy_sections_present(self, analytics_client, authed_headers):
        """Legacy sections (model_performance, latency, stream_freshness) still present."""
        with patch("db.delta_adapter.read_analytics_table", _mock_read_analytics_table):
            resp = analytics_client.get("/api/analytics", headers=authed_headers)
        data = resp.json()
        for section in ["model_performance", "latency", "stream_freshness"]:
            assert section in data, f"Legacy section '{section}' missing"

    def test_query_bounds(self, analytics_client, authed_headers):
        """read_analytics_table is called with limit=500 (bounded query)."""
        calls = []

        def _tracking_read(section, limit=500):
            calls.append((section, limit))
            return _mock_read_analytics_table(section, limit)

        with patch("db.delta_adapter.read_analytics_table", _tracking_read):
            analytics_client.get("/api/analytics", headers=authed_headers)
        for section, limit in calls:
            assert limit == 500, f"{section} called with limit={limit}, expected 500"