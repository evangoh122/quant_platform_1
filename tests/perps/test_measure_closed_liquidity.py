"""Tests for scripts/perps/measure_closed_liquidity.py (offline only).

Recorded 1h candle fixtures cover a Labor Day weekend (Monday holiday) and a
new/sparse instrument.  All expectations come from the production helpers.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from urllib import request as urlrequest

import pytest

from config.data_sources import DATA_SOURCES, validate_data_source
from config.perp_universe import load_perp_universe
from scripts.perps import measure_closed_liquidity as measure

UTC = timezone.utc
_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "perps" / "liquidity_candles"
_REAL_CONFIG = Path(__file__).resolve().parents[2] / "config" / "perp_universe.yaml"


def _candles(name: str):
    return measure.load_fixture_candles(_FIXTURES, name)


def test_tier_thresholds():
    assert measure.tier_for_weekend_usd_per_h(250_000) == "A"
    assert measure.tier_for_weekend_usd_per_h(249_999) == "B"
    assert measure.tier_for_weekend_usd_per_h(50_000) == "B"
    assert measure.tier_for_weekend_usd_per_h(49_999) == "C"
    assert measure.tier_for_weekend_usd_per_h(10_000) == "C"
    assert measure.tier_for_weekend_usd_per_h(9_999) == "D"


def test_weekend_window_spans_a_monday_holiday():
    windows = measure.weekend_windows_for(date(2026, 9, 1), date(2026, 9, 10))
    assert len(windows) == 1
    start, end = windows[0]
    # Labor Day 2026-09-07: Friday close -> Tuesday 09:30 ET open.
    assert start == datetime(2026, 9, 4, 20, 0, tzinfo=UTC)
    assert end == datetime(2026, 9, 8, 13, 30, tzinfo=UTC)
    assert measure.weekend_windows_for(date(2026, 9, 4), date(2026, 9, 8)) == windows


def test_labor_day_bars_are_weekend_not_session():
    windows = measure.weekend_windows_for(date(2026, 9, 1), date(2026, 9, 10))
    candles = _candles("NVDA")
    monday = next(
        candle
        for candle in candles
        if candle.start_ts == datetime(2026, 9, 7, 15, 0, tzinfo=UTC)
    )
    assert measure.in_weekend(monday, windows) is True
    assert measure.is_regular_session(monday.start_ts) is False

    pre_open = next(
        candle
        for candle in candles
        if candle.start_ts == datetime(2026, 9, 8, 13, 0, tzinfo=UTC)
    )
    assert measure.in_weekend(pre_open, windows) is False
    assert measure.is_regular_session(pre_open.start_ts) is False

    session = next(
        candle
        for candle in candles
        if candle.start_ts == datetime(2026, 9, 8, 14, 0, tzinfo=UTC)
    )
    assert measure.in_weekend(session, windows) is False
    assert measure.is_regular_session(session.start_ts) is True


def test_measure_nvda_fixture():
    windows = measure.weekend_windows_for(date(2026, 9, 1), date(2026, 9, 10))
    result = measure.measure_candles(_candles("NVDA"), windows)
    assert result["bars"] == 98
    assert result["weekend_bars"] == 89
    assert result["first_bar"] == "2026-09-04"
    assert result["weekend_usd_per_h"] == pytest.approx(300_000 * 85 / 89)
    assert result["zero_volume_weekend_share"] == pytest.approx(4 / 89)
    assert result["closed_usd_per_h"] > 0


def test_sparse_and_new_flags_from_fixture():
    universe = load_perp_universe()
    windows = measure.weekend_windows_for(
        universe.liquidity_window.start, universe.liquidity_window.end
    )
    measurement = measure.measure_candles(_candles("KSTR"), windows)
    assert measurement["first_bar"] == "2026-09-17"
    assert measurement["weekend_bars"] == 65
    assert measurement["zero_volume_weekend_share"] == pytest.approx(20 / 65)
    assert measurement["weekend_usd_per_h"] == pytest.approx(12_000 * 45 / 65)

    proposal = measure.build_proposal(
        universe,
        {"xyz:KSTR": measurement},
        window_start=universe.liquidity_window.start,
        window_end=universe.liquidity_window.end,
        generated_at=datetime(2026, 10, 22, tzinfo=UTC),
        mode="fixtures",
    )
    row = next(row for row in proposal["companies"] if row["id"] == "KSTR")
    assert row["proposed_tier"] == "D"
    assert row["proposed_flags"] == ["new", "sparse"]
    assert row["zero_volume_weekend_share"] == pytest.approx(20 / 65, abs=1e-4)
    assert proposal["commodities"]
    assert all(row["proposed_tier"] is None for row in proposal["commodities"])


def test_dry_run_makes_zero_network_calls(monkeypatch, capsys):
    calls = []

    def explode(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("dry-run attempted network access")

    monkeypatch.setattr(urlrequest, "urlopen", explode)
    assert measure.main(["--dry-run"]) == 0
    captured = capsys.readouterr().out
    assert calls == []
    assert "mode: dry-run" in captured
    assert "planned requests: 86" in captured
    assert "config/perp_universe.yaml is never modified" in captured


def test_fixture_mode_writes_proposal_and_never_edits_config(
    tmp_path, monkeypatch, capsys
):
    config_before = _REAL_CONFIG.read_bytes()
    calls = []

    def explode(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("fixture mode attempted network access")

    monkeypatch.setattr(urlrequest, "urlopen", explode)
    out = tmp_path / "proposal.json"
    assert (
        measure.main(
            [
                "--candles-dir",
                str(_FIXTURES),
                "--symbols",
                "NVDA,KSTR",
                "--out",
                str(out),
            ]
        )
        == 0
    )
    assert calls == []
    assert _REAL_CONFIG.read_bytes() == config_before
    proposal = json.loads(out.read_text(encoding="utf-8"))
    assert proposal["mode"] == "fixtures"
    assert proposal["window"]["start"] == "2026-08-26"
    assert "is not modified" in proposal["note"]
    rows = {row["id"]: row for row in proposal["companies"]}
    assert rows["NVDA"]["proposed_tier"] == "A"
    assert rows["KSTR"]["proposed_flags"] == ["new", "sparse"]
    assert rows["SNDK"]["proposed_tier"] is None
    assert len(proposal["commodities"]) == 8
    assert "wrote" in capsys.readouterr().out


def test_live_and_dry_run_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        measure.main(["--live", "--dry-run"])


def test_live_and_fixtures_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        measure.main(["--live", "--candles-dir", str(_FIXTURES)])


def test_parse_rejects_malformed_payload():
    with pytest.raises(measure.MeasureError, match="must be a list"):
        measure.parse_candle_payload({"t": 1})
    with pytest.raises(measure.MeasureError, match="missing 'c'"):
        measure.parse_candle_payload(
            [{"t": 0, "T": 1, "o": 1, "h": 1, "l": 1, "v": 1}]
        )


def test_rate_limiter_caps_at_two_requests_per_second():
    limiter = measure.RateLimiter(2.0)
    assert limiter.min_interval == pytest.approx(0.5)
    with pytest.raises(measure.MeasureError, match="<= 2.0"):
        measure.RateLimiter(3.0)


# ---------------------------------------------------------------------------
# data_source on every proposal record (owner rule 2026-10-22)
# ---------------------------------------------------------------------------


def test_proposal_rows_carry_the_universe_data_source():
    universe = load_perp_universe()
    windows = measure.weekend_windows_for(
        universe.liquidity_window.start, universe.liquidity_window.end
    )
    measurement = measure.measure_candles(_candles("NVDA"), windows)
    proposal = measure.build_proposal(
        universe,
        {"xyz:NVDA": measurement},
        window_start=universe.liquidity_window.start,
        window_end=universe.liquidity_window.end,
        generated_at=datetime(2026, 10, 22, tzinfo=UTC),
        mode="fixtures",
    )
    expected = {
        row.symbol: row.data_source
        for row in (*universe.companies, *universe.commodities)
    }
    rows = proposal["companies"] + proposal["commodities"]
    assert len(rows) == len(expected)
    for row in rows:
        assert row["data_source"] == expected[row["symbol"]]
        assert validate_data_source(row["data_source"]) == row["data_source"]
    assert {row["data_source"] for row in rows} == {"hyperliquid"}


def test_proposal_row_rejects_an_unknown_data_source():
    # Mutation target: a builder that writes any string must fail this test.
    measure_universe = load_perp_universe()
    windows = measure.weekend_windows_for(
        measure_universe.liquidity_window.start,
        measure_universe.liquidity_window.end,
    )
    measurement = measure.measure_candles(_candles("NVDA"), windows)
    company = measure_universe.companies[0]
    with pytest.raises(measure.MeasureError, match="data_source"):
        measure._proposal_row(
            identifier=company.ticker,
            symbol=company.symbol,
            underlying_type=company.underlying_type,
            data_source="polygon",
            current_tier=company.tier,
            current_flags=company.flags,
            measurement=measurement,
            window_start=measure_universe.liquidity_window.start,
        )
    for row in measure.build_proposal(
        measure_universe,
        {},
        window_start=measure_universe.liquidity_window.start,
        window_end=measure_universe.liquidity_window.end,
        generated_at=datetime(2026, 10, 22, tzinfo=UTC),
        mode="fixtures",
    )["companies"]:
        assert row["data_source"] in DATA_SOURCES
