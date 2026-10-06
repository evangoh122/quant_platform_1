"""Tests for /api/positioning/cot endpoint.

Verifies:
- bad asset_class → 422
- weeks out of range → 422
- SQL is parameterized (no f-string interpolation of user input)
- rows with release_ts in the future are excluded (mutation: drop release filter → fails)
- auth dependency present
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest


@pytest.fixture
def client(fake_lakebase):
    from fastapi.testclient import TestClient

    from api.main import create_app

    return TestClient(create_app())


def _mock_read_sql(sql, params=None):
    """Capture SQL and return controlled data."""
    return []


def test_bad_asset_class_returns_422(client):
    """Invalid asset_class should be rejected."""
    resp = client.get(
        "/api/positioning/cot?asset_class=INVALID",
        headers={"x-forwarded-email": "u@test.com"},
    )
    assert resp.status_code == 422
    assert "invalid asset_class" in resp.json()["detail"]


def test_weeks_too_low_returns_422(client):
    """weeks < 4 should be rejected."""
    resp = client.get(
        "/api/positioning/cot?asset_class=equity_index&weeks=2",
        headers={"x-forwarded-email": "u@test.com"},
    )
    assert resp.status_code == 422


def test_weeks_too_high_returns_422(client):
    """weeks > 520 should be rejected."""
    resp = client.get(
        "/api/positioning/cot?asset_class=equity_index&weeks=600",
        headers={"x-forwarded-email": "u@test.com"},
    )
    assert resp.status_code == 422


def test_sql_uses_named_params_not_fstring(client):
    """SQL must use :asset_class and :cutoff placeholders, not f-string interpolation."""
    captured_calls = []

    def _capture_read_sql(sql, params=None):
        captured_calls.append({"sql": sql, "params": params})
        return []

    with patch("db.delta_adapter.read_sql", side_effect=_capture_read_sql):
        resp = client.get(
            "/api/positioning/cot?asset_class=equity_index&weeks=52",
            headers={"x-forwarded-email": "u@test.com"},
        )

    assert resp.status_code == 200
    assert len(captured_calls) == 2

    weekly_call = captured_calls[0]
    contracts_call = captured_calls[1]

    # Weekly SQL should reference :asset_class and :cutoff, not have "equity_index" embedded
    assert ":asset_class" in weekly_call["sql"]
    assert ":cutoff" in weekly_call["sql"]
    assert "equity_index" not in weekly_call["sql"]
    assert weekly_call["params"]["asset_class"] == "equity_index"
    assert "cutoff" in weekly_call["params"]

    # Contracts SQL should reference :asset_class and :now
    assert ":asset_class" in contracts_call["sql"]
    assert ":now" in contracts_call["sql"]
    assert "equity_index" not in contracts_call["sql"]
    assert contracts_call["params"]["asset_class"] == "equity_index"


def test_release_ts_filter_excludes_future_rows(client):
    """The contracts query must filter release_ts <= now(). Mutation: removing
    the filter should change the SQL (we verify the WHERE clause is present)."""
    captured_calls = []

    def _capture_read_sql(sql, params=None):
        captured_calls.append({"sql": sql, "params": params})
        return []

    with patch("db.delta_adapter.read_sql", side_effect=_capture_read_sql):
        resp = client.get(
            "/api/positioning/cot?asset_class=rate",
            headers={"x-forwarded-email": "u@test.com"},
        )

    assert resp.status_code == 200
    contracts_sql = captured_calls[1]["sql"].upper()
    # Must contain the release_ts filter
    assert "RELEASE_TS" in contracts_sql
    assert "<=" in contracts_sql or "< =" in contracts_sql


def test_weekly_query_excludes_future_information_available(client):
    """The weekly COT query must filter information_available_ts <= now.
    Mutation: dropping the <= :now predicate should fail this test."""
    captured_calls = []

    def _capture_read_sql(sql, params=None):
        captured_calls.append({"sql": sql, "params": params})
        return []

    with patch("db.delta_adapter.read_sql", side_effect=_capture_read_sql):
        resp = client.get(
            "/api/positioning/cot?asset_class=equity_index&weeks=52",
            headers={"x-forwarded-email": "u@test.com"},
        )

    assert resp.status_code == 200
    weekly_sql = captured_calls[0]["sql"].upper()
    # Must contain the information_available_ts upper-bound filter
    assert "INFORMATION_AVAILABLE_TS" in weekly_sql
    assert "<=" in weekly_sql or "< =" in weekly_sql
    # Must pass a :now parameter
    assert "now" in captured_calls[0]["params"]


def test_contracts_only_latest_released_week(client):
    """The contracts query must return only the latest released week.
    Mutation: dropping the latest-week subquery should fail this test."""
    captured_calls = []

    def _capture_read_sql(sql, params=None):
        captured_calls.append({"sql": sql, "params": params})
        return []

    with patch("db.delta_adapter.read_sql", side_effect=_capture_read_sql):
        resp = client.get(
            "/api/positioning/cot?asset_class=rate",
            headers={"x-forwarded-email": "u@test.com"},
        )

    assert resp.status_code == 200
    contracts_sql = captured_calls[1]["sql"].upper()
    # Must contain the MAX(report_date) subquery for latest-week filtering
    assert "MAX(REPORT_DATE)" in contracts_sql
    assert "SELECT MAX(REPORT_DATE)" in contracts_sql


def test_auth_dependency_present(client):
    """Request without auth header should fail (no x-forwarded-email)."""
    resp = client.get("/api/positioning/cot?asset_class=equity_index")
    assert resp.status_code == 401


def test_valid_asset_classes_accepted(client):
    """All 6 valid asset classes should be accepted."""
    for ac in ["equity_index", "rate", "fx", "other", "crypto", "commodity"]:
        with patch("db.delta_adapter.read_sql", return_value=[]):
            resp = client.get(
                f"/api/positioning/cot?asset_class={ac}",
                headers={"x-forwarded-email": "u@test.com"},
            )
        assert resp.status_code == 200, f"asset_class={ac} returned {resp.status_code}"
        assert resp.json()["asset_class"] == ac


def test_weeks_boundary_values(client):
    """Boundary weeks=4 and weeks=520 should be accepted."""
    for w in [4, 520]:
        with patch("db.delta_adapter.read_sql", return_value=[]):
            resp = client.get(
                f"/api/positioning/cot?asset_class=fx&weeks={w}",
                headers={"x-forwarded-email": "u@test.com"},
            )
        assert resp.status_code == 200, f"weeks={w} returned {resp.status_code}"


def test_response_structure(client):
    """Response should have asset_class, weekly, contracts envelopes."""
    sample_weekly = [
        {
            "mapped_asset": "equity_index",
            "report_date": "2026-09-01",
            "information_available_ts": "2026-09-05T20:00:00Z",
            "lev_money_net": -50000,
            "lev_money_net_chg_1w": -2000,
            "lev_money_pctile_52w": 0.35,
            "lev_money_zscore_52w": -0.8,
            "asset_mgr_net": 80000,
            "asset_mgr_pctile_52w": 0.72,
            "crowding_score": 0.65,
            "regime_label": "crowded_short",
        },
    ]
    sample_contracts = [
        {
            "contract_name": "E-mini S&P 500",
            "open_interest": 2500000,
            "dealer_net": -10000,
            "asset_mgr_net": 50000,
            "lev_money_net": -30000,
            "dealer_pct_oi": -0.4,
            "asset_mgr_pct_oi": 2.0,
            "lev_money_pct_oi": -1.2,
        },
    ]

    def _mock_read_sql(sql, params=None):
        if "gold_cot_features" in sql:
            return sample_weekly
        return sample_contracts

    with patch("db.delta_adapter.read_sql", side_effect=_mock_read_sql):
        resp = client.get(
            "/api/positioning/cot?asset_class=equity_index&weeks=52",
            headers={"x-forwarded-email": "u@test.com"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["asset_class"] == "equity_index"
    assert data["weekly"]["count"] == 1
    assert data["weekly"]["empty"] is False
    assert data["weekly"]["source"] == "gold_cot_features"
    assert data["weekly"]["data"][0]["lev_money_net"] == -50000
    assert data["weekly"]["data"][0]["crowding_score"] == 0.65
    assert data["weekly"]["data"][0]["regime_label"] == "crowded_short"
    assert data["contracts"]["count"] == 1
    assert data["contracts"]["data"][0]["contract_name"] == "E-mini S&P 500"