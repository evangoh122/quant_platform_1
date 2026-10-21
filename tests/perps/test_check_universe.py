"""Tests for the report-only perp ticker check (scripts/perps/check_universe.py)."""
from __future__ import annotations

import json
from pathlib import Path

from config.perp_universe import load_perp_universe
from scripts.perps import check_universe


def _run_json(tmp_path: Path, *extra: str) -> dict:
    target = tmp_path / "check.json"
    assert check_universe.main(["--json", str(target), *extra]) == 0
    return json.loads(target.read_text(encoding="utf-8"))


def test_report_flags_etf_preferred_and_fund(tmp_path):
    report = _run_json(tmp_path)
    assert report["universe"]["companies"] == 78
    assert "KSTR" in report["summary"]["etf"]
    assert "STRC" in report["summary"]["preferred"]
    assert "BOT" in report["summary"]["fund"]


def test_report_flags_expected_unmapped_suspects(tmp_path):
    report = _run_json(tmp_path)
    unmapped = set(report["summary"]["unmapped_offline"])
    for ticker in ("BIRD", "CBRS", "SHAZ", "STRC", "KSTR"):
        assert ticker in unmapped
    assert len(report["rows"]) == 78


def test_report_never_removes_entries(tmp_path):
    _run_json(tmp_path)
    assert load_perp_universe().company_count == 78


def test_report_is_markdown_and_report_only(tmp_path, capsys):
    assert check_universe.main(["--json", str(tmp_path / "report.json")]) == 0
    output = capsys.readouterr().out
    assert "# Perp universe ticker check" in output
    assert "Report only: no entries were removed" in output


def test_custom_offline_cik_map_clears_unmapped(tmp_path):
    cik_map = tmp_path / "company_tickers.json"
    cik_map.write_text(
        json.dumps({"0": {"ticker": "BIRD", "cik_str": 123456}}),
        encoding="utf-8",
    )
    report = _run_json(tmp_path, "--cik-map", str(cik_map))
    unmapped = set(report["summary"]["unmapped_offline"])
    assert "BIRD" not in unmapped
    bird = next(row for row in report["rows"] if row["ticker"] == "BIRD")
    assert bird["ciks"] == ["0000123456"]
