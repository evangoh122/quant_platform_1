"""Tests for scripts/perps/probe_history.py (offline only).

The dry-run path must never touch the network; all network behaviour is
exercised through injected fake clients and recorded fixtures.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from urllib import request as urlrequest

import pytest

from config.data_sources import DATA_SOURCES, validate_data_source
from config.perp_universe import INSTRUMENT_TYPE, load_perp_universe
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


def test_parse_binance_listing_page_is_namespace_aware():
    page = probe.parse_binance_listing_page(
        _text_fixture("binance_vision_s3_page1.xml")
    )
    assert page.keys == (
        "data/futures/um/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2019-09.zip",
        "data/futures/um/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2019-10.zip",
    )
    assert page.common_prefixes == ()
    assert page.truncated is True
    assert page.next_marker == (
        "data/futures/um/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2019-10.zip"
    )


def test_parse_binance_listing_page_reads_common_prefixes():
    text = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        "<Prefix>data/futures/um/monthly/klines/BTCUSDT/</Prefix>"
        "<CommonPrefixes><Prefix>data/futures/um/monthly/klines/BTCUSDT/1h/</Prefix></CommonPrefixes>"
        "<CommonPrefixes><Prefix>data/futures/um/monthly/klines/BTCUSDT/1m/</Prefix></CommonPrefixes>"
        "<IsTruncated>false</IsTruncated>"
        "</ListBucketResult>"
    )
    page = probe.parse_binance_listing_page(text)
    assert page.keys == ()
    assert page.common_prefixes == (
        "data/futures/um/monthly/klines/BTCUSDT/1h/",
        "data/futures/um/monthly/klines/BTCUSDT/1m/",
    )
    assert page.truncated is False
    assert page.next_marker is None


class _PagedListingClient:
    def __init__(self) -> None:
        self.urls = []

    def get_text(self, url):
        self.urls.append(url)
        if "marker=" in url:
            return _text_fixture("binance_vision_s3_page2.xml")
        return _text_fixture("binance_vision_s3_page1.xml")


def test_fetch_binance_listing_follows_next_marker():
    prefix = "data/futures/um/monthly/klines/BTCUSDT/1h/"
    client = _PagedListingClient()
    keys = probe.fetch_binance_listing(client, prefix)
    assert keys == [
        f"{prefix}BTCUSDT-1h-2019-09.zip",
        f"{prefix}BTCUSDT-1h-2019-10.zip",
        f"{prefix}BTCUSDT-1h-2019-11.zip",
        f"{prefix}BTCUSDT-1h-2019-12.zip",
    ]
    assert len(client.urls) == 2
    assert client.urls[0].startswith(probe.BINANCE_VISION_LISTING_URL)
    assert "delimiter=/" in client.urls[0]
    assert f"prefix={prefix}" in client.urls[0]
    assert "marker=" not in client.urls[0]
    assert "marker=" in client.urls[1]


def test_fetch_binance_listing_rejects_truncated_page_without_next_marker():
    class _NoMarkerClient:
        def get_text(self, url):
            return (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
                "<IsTruncated>true</IsTruncated>"
                "</ListBucketResult>"
            )

    with pytest.raises(probe.ProbeError, match="without NextMarker"):
        probe.fetch_binance_listing(_NoMarkerClient(), "data/futures/um/monthly/")


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


def test_build_targets_covers_78_companies_8_commodities_2_controls():
    universe = load_perp_universe()
    targets = probe.build_targets(universe)
    assert len(targets) == 78 + 8 + 2 == 88
    assert sum(1 for target in targets if target.kind == "equity_perp") == 78
    assert sum(1 for target in targets if target.kind == "commodity_perp") == 8
    assert sum(1 for target in targets if target.kind == "control") == 2

    commodity_targets = [
        target for target in targets if target.kind == "commodity_perp"
    ]
    assert [target.ticker for target in commodity_targets] == [
        commodity.commodity for commodity in universe.commodities
    ]
    assert [target.symbol for target in commodity_targets] == list(
        universe.commodity_symbols
    )
    assert [target.symbol for target in targets[-2:]] == ["BTCUSDT", "ETHUSDT"]
    assert len({(target.venue, target.symbol) for target in targets}) == 88


def test_plan_covers_every_company_commodity_and_control():
    universe = load_perp_universe()
    plan = probe.plan_requests(universe, start="2025-01-01")
    hyperliquid = [
        request for request in plan if request.url == probe.HYPERLIQUID_INFO_URL
    ]
    binance = [
        request for request in plan if request.url != probe.HYPERLIQUID_INFO_URL
    ]
    hyperliquid_targets = universe.company_count + universe.commodity_count
    assert len(hyperliquid) == 3 * hyperliquid_targets == 258
    assert len(binance) == 6 * universe.control_count == 12
    assert len(plan) == 270

    bodies = [request.body for request in hyperliquid]
    candle_bodies = [body for body in bodies if body["type"] == "candleSnapshot"]
    funding_bodies = [body for body in bodies if body["type"] == "fundingHistory"]
    assert len(candle_bodies) == 2 * hyperliquid_targets
    assert len(funding_bodies) == hyperliquid_targets
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
    assert "planned requests: 270" in captured


def test_live_and_dry_run_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        probe.main(["--live", "--dry-run"])


def test_rate_limiter_caps_at_two_requests_per_second():
    limiter = probe.RateLimiter(2.0)
    assert limiter.min_interval == pytest.approx(0.5)
    with pytest.raises(probe.ProbeError, match="<= 2.0"):
        probe.RateLimiter(3.0)


def test_retry_backoff_has_injected_jitter():
    rng = random.Random(7)
    client = probe.HttpClient(
        backoff_seconds=1.0, jitter_fraction=0.5, rng=rng, max_rps=2.0
    )
    delays = [client._delay(attempt) for attempt in range(6)]
    # Exact schedule: exponential base times (1 + 0.5 * injected draw), with the
    # draws taken in attempt order, so random.Random(7) pins every wait.
    assert delays == pytest.approx(
        [
            1.1619163824165812,
            2.150849173924502,
            5.301868946079708,
            8.289745146670171,
            20.287056034453514,
            37.85102267060137,
        ]
    )
    for attempt, delay in enumerate(delays):
        base = 2 ** attempt
        assert base < delay <= base * 1.5
    # A zero jitter fraction keeps the deterministic exponential schedule.
    fixed = probe.HttpClient(
        backoff_seconds=1.0,
        jitter_fraction=0.0,
        rng=random.Random(7),
        max_rps=2.0,
    )
    assert [fixed._delay(attempt) for attempt in range(4)] == [1.0, 2.0, 4.0, 8.0]


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
    assert len(result["hyperliquid"]["commodities"]) == universe.commodity_count
    first = result["hyperliquid"]["instruments"][0]
    assert first["ticker"] == universe.companies[0].ticker
    assert first["streams"]["candle_1h"]["first_iso"] == "2025-01-01T00:00:00+00:00"
    assert first["streams"]["funding"]["first_ms"] == 1735689600000
    first_commodity = result["hyperliquid"]["commodities"][0]
    assert first_commodity["commodity"] == universe.commodities[0].commodity
    assert first_commodity["etf_kind"] in {"physical", "futures"}
    assert first_commodity["streams"]["candle_1h"]["first_iso"] == (
        "2025-01-01T00:00:00+00:00"
    )

    controls = result["binance_usdm"]["instruments"]
    assert [entry["symbol"] for entry in controls] == ["BTCUSDT", "ETHUSDT"]
    assert controls[0]["streams"]["klines_1h"]["first_day"] == "2019-09-08"
    assert controls[0]["streams"]["klines_1h"]["first_month"] == "2019-09"

    assert "current open interest only" in result["notes"]["open_interest"]


def test_probe_binance_reads_every_listing_page():
    class _PagedBinanceClient:
        def __init__(self) -> None:
            self.urls = []

        def get_text(self, url):
            self.urls.append(url)
            if "/daily/" in url:
                return _text_fixture("binance_vision_daily_listing.html")
            if "klines" not in url:
                return (
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
                    "<IsTruncated>false</IsTruncated>"
                    "</ListBucketResult>"
                )
            if "marker=" in url:
                return _text_fixture("binance_vision_s3_page2.xml")
            return _text_fixture("binance_vision_s3_page1.xml")

    universe = load_perp_universe()
    client = _PagedBinanceClient()
    out = probe.probe_binance(client, universe.controls[0])
    assert out["klines_1h"]["first_month"] == "2019-09"
    assert out["klines_1h"]["monthly_archives"] == 4
    assert out["klines_1h"]["first_day"] == "2019-09-08"
    assert out["klines_1h"]["daily_archives_in_first_month"] == 3
    assert any("marker=" in url for url in client.urls)


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
                    "tier": "A",
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
    assert "| NVDA | `xyz:NVDA` | A |" in report
    assert "2019-09-08" in report
    assert "current open interest only" in report


# ---------------------------------------------------------------------------
# data_source on every probe record (owner rule 2026-10-22)
# ---------------------------------------------------------------------------


def test_build_targets_take_data_source_from_the_validated_universe():
    universe = load_perp_universe()
    targets = probe.build_targets(universe)
    expected = [
        row.data_source
        for row in (
            *universe.companies,
            *universe.commodities,
            *universe.controls,
        )
    ]
    assert [target.data_source for target in targets] == expected
    assert {target.data_source for target in targets} == {
        "hyperliquid",
        "binance_um",
    }
    for target in targets:
        assert validate_data_source(target.data_source) == target.data_source


def test_probe_target_rejects_an_unknown_data_source():
    # Mutation target: a target that accepts any code must fail this test.
    with pytest.raises(probe.ProbeError, match="data_source"):
        probe.ProbeTarget(
            ticker="NVDA",
            venue="hyperliquid",
            symbol="xyz:NVDA",
            kind="equity_perp",
            data_source="polygon",
        )


def test_probe_live_records_carry_data_source():
    universe = load_perp_universe()
    result = probe.probe_live(
        universe,
        start="2025-01-01",
        coarse_days=60,
        max_steps=1,
        client=_FakeClient(),
    )
    instruments = result["hyperliquid"]["instruments"]
    commodities = result["hyperliquid"]["commodities"]
    controls = result["binance_usdm"]["instruments"]
    assert len(instruments) == universe.company_count
    assert all(entry["data_source"] == "hyperliquid" for entry in instruments)
    assert [entry["data_source"] for entry in commodities] == [
        commodity.data_source for commodity in universe.commodities
    ]
    assert all(entry["data_source"] == "binance_um" for entry in controls)
    for entry in instruments + commodities + controls:
        assert entry["data_source"] in DATA_SOURCES
        assert entry["instrument_type"] == INSTRUMENT_TYPE
    assert [entry["instrument_type"] for entry in instruments] == [
        company.instrument_type for company in universe.companies
    ]
    assert [entry["instrument_type"] for entry in commodities] == [
        commodity.instrument_type for commodity in universe.commodities
    ]
    assert [entry["instrument_type"] for entry in controls] == [
        control.instrument_type for control in universe.controls
    ]


def test_render_markdown_carries_data_source_per_record():
    result = {
        "generated_at": "2026-10-22T00:00:00+00:00",
        "mode": "live",
        "probe": {"start": "2025-01-01T00:00:00+00:00"},
        "hyperliquid": {
            "instruments": [
                {
                    "ticker": "NVDA",
                    "symbol": "xyz:NVDA",
                    "tier": "A",
                    "data_source": "hyperliquid",
                    "instrument_type": INSTRUMENT_TYPE,
                    "streams": {},
                }
            ],
            "commodities": [
                {
                    "commodity": "gold",
                    "symbol": "xyz:GOLD",
                    "tier": "A",
                    "data_source": "hyperliquid",
                    "instrument_type": INSTRUMENT_TYPE,
                    "etfs": ["GLD", "IAU"],
                    "etf_kind": "physical",
                    "streams": {},
                }
            ],
        },
        "binance_usdm": {
            "instruments": [
                {
                    "symbol": "BTCUSDT",
                    "data_source": "binance_um",
                    "instrument_type": INSTRUMENT_TYPE,
                    "streams": {},
                }
            ]
        },
    }
    report = probe.render_markdown(result)
    assert "| Ticker | Symbol | Tier | Data source |" in report
    assert "| NVDA | `xyz:NVDA` | A | hyperliquid |" in report
    assert "| gold | `xyz:GOLD` | A | hyperliquid |" in report
    assert "| BTCUSDT | binance_um |" in report
    assert "| Instrument type |" in report
    assert "| hyperliquid | perpetual_future |" in report
    assert "| binance_um | perpetual_future |" in report
