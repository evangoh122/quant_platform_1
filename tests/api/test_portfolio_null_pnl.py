"""tests/api/test_portfolio_null_pnl.py — Fix 3: null must not become zero.

Verifies that when ``unrealized_pnl`` / ``realized_pnl`` are NULL in the
database, the API returns JSON null (not 0) and the frontend renders "—".
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture
def client(fake_lakebase):
    from fastapi.testclient import TestClient
    from api.main import create_app
    return TestClient(create_app())


def test_null_pnl_serializes_as_json_null(client, fake_lakebase):
    """Positions with NULL unrealized_pnl/realized_pnl must serialize as null in JSON."""
    # Set up fake lakebase to return a row with null P&L
    fake_lakebase.execute = lambda q, p=None, **kw: [
        ("default", "AAPL", 100.0, 150.0, None, None, None, "2026-10-07"),
    ]

    with patch("agent.tools_retrieval.get_portfolio_positions") as mock_pos, \
         patch("agent.tools_retrieval.get_open_orders", return_value=[]):
        mock_pos.return_value = [
            {
                "account_id": "default",
                "symbol": "AAPL",
                "quantity": 100.0,
                "avg_cost": 150.0,
                "market_price": None,
                "realized_pnl": None,
                "unrealized_pnl": None,
                "updated_at": "2026-10-07",
            }
        ]
        resp = client.get("/api/portfolio", headers={"x-forwarded-email": "u@test.com"})

    assert resp.status_code == 200
    data = resp.json()
    pos = data["positions"]["data"][0]

    # These must be JSON null, not 0
    assert pos["realized_pnl"] is None, f"realized_pnl should be null, got {pos['realized_pnl']}"
    assert pos["unrealized_pnl"] is None, f"unrealized_pnl should be null, got {pos['unrealized_pnl']}"
    assert pos["market_price"] is None, f"market_price should be null, got {pos['market_price']}"


def test_non_null_pnl_serializes_as_number(client):
    """Positions with actual P&L values must serialize as numbers."""
    with patch("agent.tools_retrieval.get_portfolio_positions") as mock_pos, \
         patch("agent.tools_retrieval.get_open_orders", return_value=[]):
        mock_pos.return_value = [
            {
                "account_id": "default",
                "symbol": "MSFT",
                "quantity": 50.0,
                "avg_cost": 300.0,
                "market_price": 310.0,
                "realized_pnl": 500.0,
                "unrealized_pnl": -200.0,
                "updated_at": "2026-10-07",
            }
        ]
        resp = client.get("/api/portfolio", headers={"x-forwarded-email": "u@test.com"})

    assert resp.status_code == 200
    pos = resp.json()["positions"]["data"][0]
    assert pos["realized_pnl"] == 500.0
    assert pos["unrealized_pnl"] == -200.0


def test_mixed_null_and_realized_positions(client):
    """Mix of null and non-null P&L positions in the same portfolio."""
    with patch("agent.tools_retrieval.get_portfolio_positions") as mock_pos, \
         patch("agent.tools_retrieval.get_open_orders", return_value=[]):
        mock_pos.return_value = [
            {
                "account_id": "default",
                "symbol": "AAPL",
                "quantity": 100.0,
                "avg_cost": 150.0,
                "market_price": None,
                "realized_pnl": None,
                "unrealized_pnl": None,
                "updated_at": "2026-10-07",
            },
            {
                "account_id": "default",
                "symbol": "MSFT",
                "quantity": 50.0,
                "avg_cost": 300.0,
                "market_price": 310.0,
                "realized_pnl": 500.0,
                "unrealized_pnl": -200.0,
                "updated_at": "2026-10-07",
            },
        ]
        resp = client.get("/api/portfolio", headers={"x-forwarded-email": "u@test.com"})

    assert resp.status_code == 200
    positions = resp.json()["positions"]["data"]
    assert positions[0]["unrealized_pnl"] is None
    assert positions[1]["unrealized_pnl"] == -200.0
