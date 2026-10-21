"""Tests for scripts/perps/probe_history.py (offline only).

The dry-run path must never touch the network; all network behaviour is
exercised through injected fake clients and recorded fixtures.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib import request as urlrequest

import pytest

from config.perp_universe import load_perp_universe
from scripts.perps import probe_history as probe

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "perps"


def _json_fixture(name: str):
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def _text_fixture(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def test_parse_candles_normalises_records():
    candles = probe.parse_candles(_json_fixture("hyperliquid_candle_snapshot.json"))
    assert len(candles) == 3
    first = candles[0]
    assert first["start_ms"] == 1735689600000
    assert first["end_ms"] == 1735693199999
    assert first["symbol"] == "xyz:NVDA"
    assert first["interval"] == "1h"
    assert first["open"] == 134.50
    assert first["close"] == 135.10
    assert first["high"] == 135.75
    assert first["low"] == 134.25
    assert first["volume"] == 18422.5
    assert first["trades"] == 731
    assert candles[-1]["trades"] == 404


def test_parse_candles_rejects_non_list():
    with pytest.raises(probe.ProbeError, match="must be a list"):
        probe.parse_candles({"t": 1})


def test_parse_candles_rejects_missing_field():
    payload = _json_fixture("hyperliquid_candle_snapshot.json")
    del payload[0]["c"]
    with pytest.raises(probe.ProbeError, match="missing 'c'"):
        probe.parse_candles(payload)


def test_parse_funding_normalises_records():
    records = probe.parse_funding(
        _json_fixture("hyperliquid_funding_history.json")
    )
    assert [record["time_ms"] for record in records] == [
        1735689600000,
        1735722000000,
        1735754400000,
    ]
    assert records[0]["coin"] == "xyz:NVDA"
    assert records[0]["funding_rate"] == 0.0000125
    assert records[0]["premium"] == 0.0001
    assert records[1]["funding_rate"] == -0.0000075


def test_earliest_timestamp_extraction():
    candles = probe.parse_candles(_json_fixture("hyperliquid_candle_snapshot.json"))
    funding = probe.parse_funding(
        _json_fixture("hyperliquid_funding_history.json")
    )
    assert probe.earliest_timestamp(candles, "start_ms") == 1735689600000
    assert probe.earliest_timestamp(funding, "time_ms") == 1735689600000
    assert probe.earliest_timestamp([], "start_ms") is None


def test_earliest_timestamp_rejects_missing_key():
    with pytest.raises(probe.ProbeError, match="missing 'time_ms'"):
        probe.earliest_timestamp([{"other": 1}], "time_ms")


def test_parse_binance_monthly_listing_filters_prefix():
    keys = probe.parse_binance_listing(
        _text_fixture("binance_vision_monthly_listing.xml"),
        "data/futures/um/monthly/klines/BTCUSDT/1h/",
    )
    assert keys == [
        "data/futures/um/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2019-09.zip",
        "data/futures/um/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2019-10.zip",
        "data/futures/um/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2019-11.zip",
    ]


def test_parse_binance_daily_listing_handles_html_and_absolute_urls():
    keys = probe.parse_binance_listing(
        _text_fixture("binance_vision_daily_listing.html"),
        "data/futures/um/daily/klines/BTCUSDT/1h/",
    )
    assert keys == [
        "data/futures/um/daily/klines/BTCUSDT/1h/BTCUSDT-1h-2019-09-08.zip",
        "data/futures/um/daily/klines/BTCUSDT/1h/BTCUSDT-1h-2019-09-09.zip",
        "data/futures/um/daily/klines/BTCUSDT/1h/BTCUSDT-1h-2019-09-10.zip",
    ]


def test_plan_covers_every_company_and_control():
    universe = load_perp_universe()
    plan = probe.plan_requests(universe, start="2025-01-01")
    hyperliquid = [
        request for request in plan if request.url == probe.HYPERLIQUID_INFO_URL
    ]
    binance = [
        request for request in plan if request.url != probe.HYPERLIQUID_INFO_URL
    ]
    assert len(hyperliquid) == 3 * universe.company_count == 234
    assert len(binance) == 6 * universe.control_count == 12
    assert len(plan) == 246

    bodies = [request.body for request in hyperliquid]
    candle_bodies = [body for body in bodies if body["type"] == "candleSnapshot"]
    funding_bodies = [body for body in bodies if body["type"] == "fundingHistory"]
    assert len(candle_bodies) == 2 * universe.company_count
    assert len(funding_bodies) == universe.company_count
    assert {body["req"]["interval"] for body in candle_bodies} == {"1h", "1d"}
    assert {
        body["req"]["startTime"] for body in candle_bodies + funding_bodies
        if "req" in body
    } == {1735689600000}
    assert {body["startTime"] for body in funding_bodies} == {1735689600000}


def test_dry_run_makes_zero_network_calls(monkeypatch, capsys):
    calls = []

    def explode(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("dry-run attempted network access")

    monkeypatch.setattr(urlrequest, "urlopen", explode)
    assert probe.main(["--dry-run"]) == 0
    captured = capsys.readouterr().out
    assert calls == []
    assert "mode: dry-run" in captured
    assert "candleSnapshot" in captured
    assert "fundingHistory" in captured
    assert "BTCUSDT" in captured
    assert "ETHUSDT" in captured
    assert "planned requests: 246" in captured


def test_live_and_dry_run_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        probe.main(["--live", "--dry-run"])


def test_rate_limiter_caps_at_two_requests_per_second():
    limiter = probe.RateLimiter(2.0)
    assert limiter.min_interval == pytest.approx(0.5)
    with pytest.raises(probe.ProbeError, match="<= 2.0"):
        probe.RateLimiter(3.0)


class _FakeClient:
    def __init__(self) -> None:
        self.requests = []

    def post_json(self, url, body):
        self.requests.append((url, body))
        if body["type"] == "candleSnapshot":
            return _json_fixture("hyperliquid_candle_snapshot.json")
        return _json_fixture("hyperliquid_funding_history.json")

    def get_text(self, url):
        self.requests.append((url, None))
        if "/daily/" in url:
            return _text_fixture("binance_vision_daily_listing.html")
        return _text_fixture("binance_vision_monthly_listing.xml")


def test_probe_live_orchestrates_hyperliquid_and_binance(monkeypatch):
    universe = load_perp_universe()
    client = _FakeClient()
    result = probe.probe_live(
        universe,
        start="2025-01-01",
        coarse_days=60,
        max_steps=2,
        client=client,
    )
    assert result["mode"] == "live"
    assert len(result["hyperliquid"]["instruments"]) == universe.company_count
    first = result["hyperliquid"]["instruments"][0]
    assert first["ticker"] == universe.companies[0].ticker
    assert first["streams"]["candle_1h"]["first_iso"] == "2025-01-01T00:00:00+00:00"
    assert first["streams"]["funding"]["first_ms"] == 1735689600000

    controls = result["binance_usdm"]["instruments"]
    assert [entry["symbol"] for entry in controls] == ["BTCUSDT", "ETHUSDT"]
    assert controls[0]["streams"]["klines_1h"]["first_day"] == "2019-09-08"
    assert controls[0]["streams"]["klines_1h"]["first_month"] == "2019-09"

    assert "current open interest only" in result["notes"]["open_interest"]


def test_render_markdown_tables_and_oi_note():
    result = {
        "generated_at": "2026-10-22T00:00:00+00:00",
        "mode": "live",
        "probe": {"start": "2025-01-01T00:00:00+00:00", "coarse_days": 60, "max_steps": 60},
        "hyperliquid": {
            "instruments": [
                {
                    "ticker": "NVDA",
                    "symbol": "xyz:NVDA",
                    "tier": "liquid",
                    "streams": {
                        "candle_1h": {"first_iso": "2025-10-01T00:00:00+00:00"},
                        "candle_1d": {"first_iso": "2025-10-01T00:00:00+00:00"},
                        "funding": {"first_iso": "2025-10-01T01:00:00+00:00"},
                    },
                }
            ]
        },
        "binance_usdm": {
            "instruments": [
                {
                    "symbol": "BTCUSDT",
                    "streams": {
                        "klines_1h": {"first_day": "2019-09-08"},
                        "funding_rate": {"first_day": "2020-01-01"},
                        "metrics": {"first_day": "2020-01-01"},
                    },
                }
            ]
        },
    }
    report = probe.render_markdown(result)
    assert "| NVDA | `xyz:NVDA` | liquid |" in report
    assert "2019-09-08" in report
    assert "current open interest only" in report
