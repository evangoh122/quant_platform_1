"""Tests for /api/market/{symbol} bounded queries.

Verifies that the market route uses:
- Bounded date window (last N days, configurable, max 1000)
- Explicit row LIMIT (max 5000)
- Selected columns only (not SELECT *)
- Single options query path
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture
def client(fake_lakebase):
    from fastapi.testclient import TestClient

    from api.main import create_app

    return TestClient(create_app())


@pytest.fixture
def mock_delta_reads():
    """Patch read_delta to return controlled data."""
    def _read_delta(fn, snapshot_key=None):
        # Call the fn to verify it works, but return controlled data
        try:
            rows = fn()
        except Exception:
            rows = []
        if not rows:
            return [], "empty", "0 rows"
        return rows, "fresh", f"{len(rows)} rows"

    with patch("api.routes.market.read_delta", side_effect=_read_delta) as m:
        yield m


def test_default_days_param(client, mock_delta_reads):
    """Default days=252 should produce a bounded date window."""
    captured_kwargs = {}

    def _mock_get_market_features(symbol, start_time, end_time, *, limit=5000):
        captured_kwargs["start_time"] = start_time
        captured_kwargs["end_time"] = end_time
        captured_kwargs["limit"] = limit
        return []

    def _mock_get_options_features(symbol, expiry=None, *, limit=5000):
        captured_kwargs["opt_limit"] = limit
        return []

    with patch("agent.tools_retrieval.get_market_features", side_effect=_mock_get_market_features), \
         patch("agent.tools_retrieval.get_options_features", side_effect=_mock_get_options_features):
        resp = client.get("/api/market/AAPL", headers={"x-forwarded-email": "u@test.com"})

    assert resp.status_code == 200
    # Verify bounded window was used (not 1970-01-01)
    assert "1970" not in captured_kwargs.get("start_time", "")
    assert captured_kwargs.get("limit") == 5000
    # Options bounded by days (min(days=252, limit=5000) = 252)
    assert captured_kwargs.get("opt_limit") == 252


def test_custom_days_param(client, mock_delta_reads):
    """Custom days=30 should produce a tighter window."""
    captured_kwargs = {}

    def _mock_get_market_features(symbol, start_time, end_time, *, limit=5000):
        captured_kwargs["start_time"] = start_time
        return []

    with patch("agent.tools_retrieval.get_market_features", side_effect=_mock_get_market_features), \
         patch("agent.tools_retrieval.get_options_features", return_value=[]):
        resp = client.get("/api/market/AAPL?days=30", headers={"x-forwarded-email": "u@test.com"})

    assert resp.status_code == 200
    # The start_time should be ~30 days ago, not 1970
    assert "1970" not in captured_kwargs.get("start_time", "")


def test_days_param_max_capped(client):
    """days > 1000 should be rejected."""
    resp = client.get("/api/market/AAPL?days=2000", headers={"x-forwarded-email": "u@test.com"})
    assert resp.status_code == 422


def test_days_param_min_capped(client):
    """days < 1 should be rejected."""
    resp = client.get("/api/market/AAPL?days=0", headers={"x-forwarded-email": "u@test.com"})
    assert resp.status_code == 422


def test_limit_param_max_capped(client):
    """limit > 5000 should be rejected."""
    resp = client.get("/api/market/AAPL?limit=10000", headers={"x-forwarded-email": "u@test.com"})
    assert resp.status_code == 422


def test_options_uses_limit(client, mock_delta_reads):
    """Options query should use the limit parameter."""
    captured = {}

    def _mock_get_options_features(symbol, expiry=None, *, limit=5000):
        captured["limit"] = limit
        return []

    with patch("agent.tools_retrieval.get_market_features", return_value=[]), \
         patch("agent.tools_retrieval.get_options_features", side_effect=_mock_get_options_features):
        resp = client.get("/api/market/AAPL?limit=100", headers={"x-forwarded-email": "u@test.com"})

    assert resp.status_code == 200
    assert captured.get("limit") == 100


def test_invalid_symbol_returns_422(client):
    """Invalid symbol should return 422."""
    resp = client.get("/api/market/'; DROP TABLE --", headers={"x-forwarded-email": "u@test.com"})
    assert resp.status_code == 422


def test_options_bounded_by_days(client, mock_delta_reads):
    """Options rows bounded by min(days, limit). Custom days=50, limit=5000 → 50."""
    captured = {}

    def _mock_get_options_features(symbol, expiry=None, *, limit=5000):
        captured["limit"] = limit
        return []

    with patch("agent.tools_retrieval.get_market_features", return_value=[]), \
         patch("agent.tools_retrieval.get_options_features", side_effect=_mock_get_options_features):
        resp = client.get("/api/market/AAPL?days=50", headers={"x-forwarded-email": "u@test.com"})

    assert resp.status_code == 200
    assert captured.get("limit") == 50


def test_ohlcv_uses_event_date_and_price_basis(client, mock_delta_reads):
    """OHLCV rows use event_date (not feature_ts) and include price_basis."""
    sample_rows = [
        {"symbol": "AAPL", "event_date": "2025-01-15", "open": 150.0, "high": 155.0,
         "low": 149.0, "close": 153.0, "volume": 1000000.0, "vwap": 152.0},
    ]

    with patch("agent.tools_retrieval.get_market_features", return_value=sample_rows), \
         patch("agent.tools_retrieval.get_options_features", return_value=[]):
        resp = client.get("/api/market/AAPL", headers={"x-forwarded-email": "u@test.com"})

    assert resp.status_code == 200
    data = resp.json()
    bar = data["ohlcv"]["data"][0]
    assert bar["event_date"] == "2025-01-15"
    assert "feature_ts" not in bar
    assert bar["price_basis"] == "split_adjusted"
    assert bar["vwap"] == 152.0