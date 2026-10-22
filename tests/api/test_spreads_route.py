"""GET /api/spreads — auth, bounds, per-chart degradation and adapter contract.

The route reads through stubbed ``agent.tools_retrieval`` functions; nothing here
may reach Databricks (the session hermetic guard from ``tests/hermetic.py``
blocks any non-loopback socket, ``databricks.sdk.WorkspaceClient`` and
``databricks.sql.connect``).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

DATES = ["2024-01-02", "2024-01-03", "2024-01-04"]

REFERENCE_NOW = datetime(2024, 1, 5, 12, 0, tzinfo=timezone.utc)


class _FrozenDatetime(datetime):
    """Deterministic clock: the route's window ends on 2024-01-05."""

    @classmethod
    def now(cls, tz=None):
        return REFERENCE_NOW if tz is None else REFERENCE_NOW.astimezone(tz)


@pytest.fixture(autouse=True)
def _freeze_route_clock(monkeypatch):
    monkeypatch.setattr("api.routes.spreads.datetime", _FrozenDatetime)
    yield

CLOSES = {
    "USO": [70.0, 71.0, 77.0],
    "RSP": [100.0, 110.0, 121.0],
    "SPY": [50.0, 50.0, 50.0],
    "MAGS": [40.0, 41.0, 42.0],
    "SOXX": [20.0, 20.0, 21.0],
    "SMH": [30.0, 30.0, 30.0],
}

HEADERS = {"x-forwarded-email": "trader@example.com"}


def _equity_rows(symbol: str) -> list[dict]:
    return [
        {"symbol": symbol, "event_date": day, "close": close}
        for day, close in zip(DATES, CLOSES[symbol])
    ]


def _fed_fixture() -> list[dict]:
    rows = []
    for series_id, values in (
        ("DGS10", [4.10, 4.05, 4.20]),
        ("DGS2", [4.50, 4.00, 4.30]),
        ("T10Y2Y", [-0.40, 0.05, -0.10]),
    ):
        for day, value in zip(DATES, values):
            rows.append(
                {
                    "series_id": series_id,
                    "observation_date": day,
                    "value": value,
                    "vintage_date": "2024-01-05",
                    "ingest_ts": "2024-01-05T21:00:00Z",
                    "revision_class": "market_rate",
                }
            )
    return rows


def _stub_readers(monkeypatch, *, failing: str | None = None) -> None:
    def fake_market(symbol, start_time, end_time, *, limit=5000):
        if symbol == failing:
            raise RuntimeError("simulated source failure")
        return _equity_rows(symbol)

    def fake_fed(series_ids, start_time, end_time, *, limit=5000):
        if failing == "fed":
            raise RuntimeError("simulated source failure")
        return _fed_fixture()

    monkeypatch.setattr("agent.tools_retrieval.get_market_features", fake_market)
    monkeypatch.setattr("agent.tools_retrieval.get_fed_series", fake_fed)


def _charts(payload: dict) -> dict[str, dict]:
    return {chart["chart_id"]: chart for chart in payload["charts"]}


# ── 6. route behaviour ──────────────────────────────────────────────────────
def test_spreads_requires_auth(client, fake_lakebase):
    response = client.get("/api/spreads")
    assert response.status_code == 401


@pytest.mark.parametrize("days", [0, 1001, -5])
def test_days_outside_bounds_is_422(client, fake_lakebase, monkeypatch, days):
    _stub_readers(monkeypatch)
    response = client.get(f"/api/spreads?days={days}", headers=HEADERS)
    assert response.status_code == 422


def test_returns_five_charts_with_points_and_freshness(client, fake_lakebase, monkeypatch):
    _stub_readers(monkeypatch)

    response = client.get("/api/spreads?days=30", headers=HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["days"] == 30
    assert payload["window_start"] < payload["window_end"]
    assert [chart["chart_id"] for chart in payload["charts"]] == [
        "uso_price",
        "treasury_yields",
        "rsp_spy",
        "mags_soxx",
        "mags_smh",
    ]
    charts = _charts(payload)
    for chart in charts.values():
        assert chart["source"]
        assert chart["freshness"]["table"]
        assert chart["freshness"]["state"] == "fresh"
        assert chart["empty"] is False
        assert chart["first_common_date"]
        assert "dropped_dates" in chart
        for series in chart["series"]:
            assert series["points"]
            for point in series["points"]:
                assert isinstance(point, list) and len(point) == 2
                assert isinstance(point[0], str) and isinstance(point[1], float)


def test_uso_chart_is_a_price_not_an_index(client, fake_lakebase, monkeypatch):
    _stub_readers(monkeypatch)

    payload = client.get("/api/spreads", headers=HEADERS).json()
    uso = _charts(payload)["uso_price"]

    assert uso["kind"] == "price"
    assert uso["series"][0]["points"][-1] == ["2024-01-04", 77.0]
    assert uso["series"][0]["latest_value"] == 77.0


def test_relative_chart_is_rebased_to_100_not_the_raw_ratio(client, fake_lakebase, monkeypatch):
    _stub_readers(monkeypatch)

    payload = client.get("/api/spreads", headers=HEADERS).json()
    rsp_spy = _charts(payload)["rsp_spy"]
    series = rsp_spy["series"][0]

    # Raw RSP/SPY ratio would start at 2.0 (100/50); the rebased index starts at 100.
    assert series["points"][0][1] == 100.0
    assert series["points"][-1][1] == pytest.approx(121.0)
    assert series["window_pct_change"] == pytest.approx(21.0)
    assert "rebased to 100" in rsp_spy["subtitle"]
    assert "RSP outperformed SPY" in rsp_spy["caption"]
    assert rsp_spy["dropped_dates"] == 0


def test_yield_chart_has_two_lines_and_a_10s2s_tile(client, fake_lakebase, monkeypatch):
    _stub_readers(monkeypatch)

    payload = client.get("/api/spreads", headers=HEADERS).json()
    yields = _charts(payload)["treasury_yields"]

    assert [series["key"] for series in yields["series"]] == ["DGS10", "DGS2"]
    assert yields["unit"] == "%"
    tile = yields["tile"]
    assert tile["label"] == "10s2s"
    assert tile["as_of"] == "2024-01-04"
    # 4.20 - 4.30 = -0.10 on the latest common date
    assert tile["value"] == pytest.approx(-0.10)
    assert len(tile["points"]) == 3


def test_freshness_detail_flags_the_weekday_approximation(client, fake_lakebase, monkeypatch):
    _stub_readers(monkeypatch)

    payload = client.get("/api/spreads", headers=HEADERS).json()

    for chart in payload["charts"]:
        assert "weekday approximation (calendar_limited)" in chart["freshness"]["detail"]


def test_one_failing_source_degrades_only_its_charts(client, fake_lakebase, monkeypatch):
    _stub_readers(monkeypatch, failing="MAGS")

    response = client.get("/api/spreads", headers=HEADERS)

    assert response.status_code == 200
    charts = _charts(response.json())
    assert charts["uso_price"]["freshness"]["state"] == "fresh"
    assert charts["treasury_yields"]["freshness"]["state"] == "fresh"
    assert charts["rsp_spy"]["freshness"]["state"] == "fresh"
    for chart_id in ("mags_soxx", "mags_smh"):
        assert charts[chart_id]["freshness"]["state"] == "unavailable"
        assert charts[chart_id]["empty"] is True
        assert charts[chart_id]["series"][0]["points"] == []


def test_fed_failure_degrades_only_the_yield_chart(client, fake_lakebase, monkeypatch):
    _stub_readers(monkeypatch, failing="fed")

    response = client.get("/api/spreads", headers=HEADERS)

    assert response.status_code == 200
    charts = _charts(response.json())
    assert charts["treasury_yields"]["freshness"]["state"] == "unavailable"
    assert charts["treasury_yields"]["tile"]["value"] is None
    assert charts["uso_price"]["freshness"]["state"] == "fresh"
    assert charts["rsp_spy"]["freshness"]["state"] == "fresh"


# ── adapter contract ────────────────────────────────────────────────────────
def test_fed_query_is_parameterised_with_an_explicit_column_list():
    from db.delta_adapter import _build_fed_series_query

    sql, params = _build_fed_series_query(["DGS10", "DGS2"], "2024-01-01", "2024-12-31")

    assert "bronze_fed_series" in sql
    # Series ids are bind parameters, never interpolated into SQL.
    assert "DGS10" not in sql and "DGS2" not in sql
    assert params["series_id_0"] == "DGS10"
    assert params["series_id_1"] == "DGS2"
    assert params["start_ts"] == "2024-01-01"
    assert params["end_ts"] == "2024-12-31"
    assert "observation_date BETWEEN :start_ts AND :end_ts" in sql
    assert "SELECT *" not in sql


def test_fed_series_warehouse_path_uses_bind_params_and_a_bound_limit(monkeypatch):
    from db import delta_adapter

    captured = {}

    def fake_query(query, params=None, *, limit=1000):
        captured.update(query=query, params=params, limit=limit)
        return [{"series_id": "DGS10", "observation_date": "2024-01-02", "value": 4.1}]

    monkeypatch.setattr(delta_adapter, "_has_pyspark", False)
    monkeypatch.setattr(delta_adapter, "_warehouse_query", fake_query)

    rows = delta_adapter.fed_series(["DGS10"], "2024-01-01", "2024-01-31", limit=25)

    assert rows == [{"series_id": "DGS10", "observation_date": "2024-01-02", "value": 4.1}]
    assert captured["params"] == {
        "series_id_0": "DGS10",
        "start_ts": "2024-01-01",
        "end_ts": "2024-01-31",
    }
    assert captured["limit"] == 25
    assert "DGS10" not in captured["query"]


def test_get_fed_series_rejects_series_outside_the_allow_list():
    from agent.tools_retrieval import get_fed_series

    with pytest.raises(ValueError):
        get_fed_series(["GDP"], "2024-01-01", "2024-12-31")
    with pytest.raises(ValueError):
        get_fed_series(["DGS10; DROP TABLE users"], "2024-01-01", "2024-12-31")
    assert get_fed_series([], "2024-01-01", "2024-12-31") == []


def test_get_fed_series_normalises_and_deduplicates_ids(monkeypatch):
    from db import delta_adapter

    captured = {}

    def fake_query(query, params=None, *, limit=1000):
        captured.update(params=params)
        return []

    monkeypatch.setattr(delta_adapter, "_has_pyspark", False)
    monkeypatch.setattr(delta_adapter, "_warehouse_query", fake_query)

    from agent.tools_retrieval import get_fed_series

    get_fed_series([" dgs10 ", "DGS10", "dgs2"], "2024-01-01", "2024-01-31")

    assert captured["params"]["series_id_0"] == "DGS10"
    assert captured["params"]["series_id_1"] == "DGS2"
    assert "series_id_2" not in captured["params"]


# ── 7. hermetic: a real Databricks path must be impossible ──────────────────
def test_real_databricks_read_is_blocked(monkeypatch):
    from db import delta_adapter
    from tests.hermetic import HermeticViolation

    monkeypatch.setattr(delta_adapter, "_has_pyspark", False)

    with pytest.raises((HermeticViolation, ImportError)):
        delta_adapter.fed_series(["DGS10"], "2024-01-01", "2024-02-01", limit=5)


def test_route_never_calls_the_warehouse(client, fake_lakebase, monkeypatch):
    """With readers stubbed, any attempt to touch the warehouse fails the test."""
    from db import delta_adapter

    def explode(*args, **kwargs):
        raise AssertionError("route reached the SQL warehouse")

    monkeypatch.setattr(delta_adapter, "_warehouse_query", explode)
    monkeypatch.setattr(delta_adapter, "_get_warehouse_connection", explode)
    _stub_readers(monkeypatch)

    response = client.get("/api/spreads", headers=HEADERS)

    assert response.status_code == 200
    assert len(response.json()["charts"]) == 5
