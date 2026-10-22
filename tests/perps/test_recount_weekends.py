"""Tests for scripts/perps/recount_weekends.py (offline, stdlib only).

The small fixture is a hand-built probe document with one long-history
instrument, one late listing and one instrument the probe could not resolve.
The recorded 2026-10-21 probe is also asserted when it is present in
``.agents/requests/`` so the plan's numbers stay tied to the measurement.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from scripts.perps import recount_weekends as recount

UTC = timezone.utc
_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "perps"
    / "history_probe_small.json"
)
_RECORDED_PROBE = (
    Path(__file__).resolve().parents[2]
    / ".agents"
    / "requests"
    / "FACTS-perps-history-probe-2026-10-21.json"
)


def _document():
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def test_friday_helpers():
    assert recount.first_friday_on_or_after(date(2026, 1, 9)) == date(2026, 1, 9)
    assert recount.first_friday_on_or_after(date(2026, 1, 10)) == date(2026, 1, 16)
    assert recount.weekend_ids(date(2026, 1, 9), date(2026, 1, 23)) == [
        date(2026, 1, 9),
        date(2026, 1, 16),
        date(2026, 1, 23),
    ]
    assert recount.weekend_ids(date(2026, 1, 10), date(2026, 1, 15)) == []
    # A single-weekend range is inclusive on both ends (the last closed weekend
    # must still count).
    assert recount.weekend_ids(date(2026, 10, 16), date(2026, 10, 16)) == [
        date(2026, 10, 16)
    ]
    assert recount.count_weekends(date(2026, 1, 5), date(2026, 1, 12)) == 1


def test_last_weekend_is_the_last_friday_strictly_before_the_probe():
    assert recount.last_friday_before(
        datetime(2026, 10, 21, 20, 0, tzinfo=UTC)
    ) == date(2026, 10, 16)
    # A probe generated ON a Friday must not claim that still-open weekend.
    assert recount.last_friday_before(
        datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
    ) == date(2026, 10, 9)


def test_recount_on_the_fixture():
    report = recount.build_report(_document())
    assert report["last_weekend_id"] == "2026-10-16"
    one_day = report["streams"][recount.STREAM_1D]
    one_hour = report["streams"][recount.STREAM_1H]
    assert one_day["company_weekends"] == 48
    assert one_day["distinct_weekends"] == 41
    assert one_day["first_weekend_id"] == "2026-01-09"
    assert one_hour["company_weekends"] == 37
    assert one_hour["distinct_weekends"] == 30
    assert one_hour["first_weekend_id"] == "2026-03-27"
    assert one_hour["instruments_without_data"] == 1
    assert report["per_instrument"][recount.STREAM_1H]["NODATA"] == 0
    # LATE's first candle is the Thursday before the final weekend: exactly one
    # weekend is buildable (the last one), so the inclusive end bound matters.
    assert report["per_instrument"][recount.STREAM_1H]["LATE"] == 1
    floor = report["one_hour_floor"]
    assert floor["weekends_unbuildable_from_1h"] == 11
    assert floor["company_weekends_unbuildable_from_1h"] == 11
    assert "2026-03-20" in floor["unbuildable_weekends_before_1h_floor"]
    assert "2026-03-27" not in floor["unbuildable_weekends_before_1h_floor"]


def test_effective_n_is_the_weekend_count_not_the_row_count():
    report = recount.build_report(_document())
    power = report["power"]
    assert power["effective_n"] == 30
    assert power["pooled_rows"] == 37
    assert power["mde"]["partial_r"] == pytest.approx(0.5392, abs=1e-4)
    assert power["mde"]["delta_r2"] == pytest.approx(0.2907, abs=1e-4)
    # Pooling rows inside a weekend understates the detectable effect.
    assert power["pooled_rows_mde"]["partial_r"] < power["mde"]["partial_r"]


def test_mde_uses_the_fisher_z_quantiles():
    assert recount._z_quantile(0.975) == pytest.approx(1.959964, abs=1e-6)
    assert recount._z_quantile(0.80) == pytest.approx(0.841621, abs=1e-6)
    assert recount._z_quantile(0.05) == pytest.approx(-1.644854, abs=1e-6)
    with pytest.raises(recount.RecountError, match="neff"):
        recount.mde(4)


def test_rejects_naive_and_malformed_probe_documents():
    with pytest.raises(recount.RecountError, match="no UTC offset"):
        recount.parse_utc("2026-10-21T20:00:52")
    document = _document()
    del document["generated_at"]
    with pytest.raises(recount.RecountError, match="generated_at"):
        recount.build_report(document)
    document = _document()
    document["hyperliquid"]["instruments"][0]["streams"]["candle_1h"]["first_iso"] = (
        "2026-03-27T09:00:00"
    )
    with pytest.raises(recount.RecountError, match="no UTC offset"):
        recount.build_report(document)
    document = _document()
    document["hyperliquid"]["instruments"] = []
    with pytest.raises(recount.RecountError, match="instruments"):
        recount.build_report(document)


def test_cli_writes_json_and_markdown(tmp_path):
    out_json = tmp_path / "panel.json"
    out_md = tmp_path / "panel.md"
    assert (
        recount.main(
            [
                "--probe",
                str(_FIXTURE),
                "--out-json",
                str(out_json),
                "--out-md",
                str(out_md),
            ]
        )
        == 0
    )
    report = json.loads(out_json.read_text(encoding="utf-8"))
    assert report["streams"][recount.STREAM_1H]["company_weekends"] == 37
    markdown = out_md.read_text(encoding="utf-8")
    assert "1h retention floor" in markdown
    assert "Effective N = 30" in markdown


def test_cli_rejects_a_missing_probe(tmp_path):
    assert recount.main(["--probe", str(tmp_path / "absent.json")]) == 2


@pytest.mark.skipif(
    not _RECORDED_PROBE.is_file(), reason="recorded 2026-10-21 probe not present"
)
def test_recorded_2026_10_21_probe_recounts_1871_and_1538_company_weekends():
    # Reproduces the numbers quoted in docs/data/PERPS_WEEKEND_PLAN.md §6.1:
    # 1d-based 1,871 company-weekends vs 1h-based 1,538 over 30 weekends.
    report = recount.build_report(
        json.loads(_RECORDED_PROBE.read_text(encoding="utf-8"))
    )
    assert report["streams"][recount.STREAM_1D]["company_weekends"] == 1871
    assert report["streams"][recount.STREAM_1H]["company_weekends"] == 1538
    assert report["streams"][recount.STREAM_1H]["distinct_weekends"] == 30
    assert report["streams"][recount.STREAM_1D]["distinct_weekends"] == 49
    assert report["one_hour_floor"]["weekends_unbuildable_from_1h"] == 19
    assert report["power"]["effective_n"] == 30
