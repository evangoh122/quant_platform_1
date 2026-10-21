"""Tests for the typed perp-universe loader (config/perp_universe.py).

Expectations are derived from the production loader and the checked-in
configuration; no validation logic is re-implemented here.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from config.perp_universe import (
    ALLOWED_DEXES,
    ALLOWED_TIERS,
    CONTROL_VENUE,
    EQUITY_VENUE,
    PerpUniverseError,
    load_perp_universe,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REAL_CONFIG = _REPO_ROOT / "config" / "perp_universe.yaml"


def _base_document():
    return yaml.safe_load(_REAL_CONFIG.read_text(encoding="utf-8"))


def _write_document(tmp_path: Path, document) -> Path:
    target = tmp_path / "perp_universe.yaml"
    target.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return target


def test_real_file_loads_all_78_companies():
    universe = load_perp_universe(_REAL_CONFIG)
    assert universe.version == 1
    assert universe.company_count == 78
    assert universe.control_count == 2
    assert universe.path == _REAL_CONFIG
    assert [control.symbol for control in universe.controls] == [
        "BTCUSDT",
        "ETHUSDT",
    ]
    assert len(set(universe.tickers)) == 78
    for company in universe.companies:
        assert company.venue == EQUITY_VENUE
        assert company.dex in ALLOWED_DEXES
        assert company.tier in ALLOWED_TIERS
        assert company.symbol == f"{company.dex}:{company.ticker}"


def test_controls_are_binance_usdm():
    universe = load_perp_universe(_REAL_CONFIG)
    assert {control.venue for control in universe.controls} == {CONTROL_VENUE}


def test_instruments_include_companies_then_controls():
    universe = load_perp_universe(_REAL_CONFIG)
    instruments = universe.instruments
    assert len(instruments) == 80
    assert instruments[0] == (
        universe.companies[0].venue,
        universe.companies[0].symbol,
    )
    assert instruments[-1] == (CONTROL_VENUE, "ETHUSDT")


def test_env_override_is_honoured(tmp_path, monkeypatch):
    target = _write_document(tmp_path, _base_document())
    monkeypatch.setenv("PERP_UNIVERSE_YAML", str(target))
    universe = load_perp_universe()
    assert universe.company_count == 78
    assert universe.path == target


def test_rejects_duplicate_ticker(tmp_path):
    document = _base_document()
    duplicate = document["companies"][0]
    document["companies"][1]["ticker"] = duplicate["ticker"]
    document["companies"][1]["symbol"] = (
        f"{document['companies'][1]['dex']}:{duplicate['ticker']}"
    )
    with pytest.raises(PerpUniverseError, match="duplicate ticker"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_bad_symbol_with_dash(tmp_path):
    # Target NVDA itself so a permissive loader would really accept the value
    # (a mutation that only relaxes the separator must be killed here).
    document = _base_document()
    nvda = next(company for company in document["companies"] if company["ticker"] == "NVDA")
    nvda["symbol"] = "xyz-NVDA"
    with pytest.raises(PerpUniverseError, match="must look like"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_symbol_ticker_mismatch(tmp_path):
    document = _base_document()
    document["companies"][0]["symbol"] = "xyz:TSLA"
    with pytest.raises(PerpUniverseError, match="does not match ticker field"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_symbol_dex_mismatch(tmp_path):
    document = _base_document()
    document["companies"][0]["symbol"] = "para:NVDA"
    with pytest.raises(PerpUniverseError, match="dex prefix"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_missing_controls(tmp_path):
    document = _base_document()
    del document["controls"]
    with pytest.raises(PerpUniverseError, match="missing required field"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_empty_controls(tmp_path):
    document = _base_document()
    document["controls"] = []
    with pytest.raises(PerpUniverseError, match="controls"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_missing_required_control(tmp_path):
    document = _base_document()
    document["controls"] = [{"venue": "binance_usdm", "symbol": "BTCUSDT"}]
    with pytest.raises(PerpUniverseError, match="missing required control"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_duplicate_control(tmp_path):
    document = _base_document()
    document["controls"].append(copy.deepcopy(document["controls"][0]))
    with pytest.raises(PerpUniverseError, match="duplicate symbol"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_control_on_equity_venue(tmp_path):
    document = _base_document()
    document["controls"][0]["venue"] = "hyperliquid"
    with pytest.raises(PerpUniverseError, match="for controls"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_missing_version(tmp_path):
    document = _base_document()
    del document["version"]
    with pytest.raises(PerpUniverseError, match="version"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_bad_version(tmp_path):
    document = _base_document()
    document["version"] = 0
    with pytest.raises(PerpUniverseError, match="version"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_bad_selected_at(tmp_path):
    document = _base_document()
    document["selected_at"] = "21-10-2026"
    with pytest.raises(PerpUniverseError, match="ISO date"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_unknown_dex(tmp_path):
    document = _base_document()
    document["companies"][0]["dex"] = "foo"
    document["companies"][0]["symbol"] = "foo:NVDA"
    with pytest.raises(PerpUniverseError, match="dex"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_unknown_tier(tmp_path):
    document = _base_document()
    document["companies"][0]["tier"] = "mega"
    with pytest.raises(PerpUniverseError, match="tier"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_unknown_company_field(tmp_path):
    document = _base_document()
    document["companies"][0]["unexpected"] = 1
    with pytest.raises(PerpUniverseError, match="unknown field"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_negative_liquidity(tmp_path):
    document = _base_document()
    document["companies"][0]["vol_24h_usd"] = -1
    with pytest.raises(PerpUniverseError, match=">= 0"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_malformed_alternate(tmp_path):
    document = _base_document()
    document["companies"][0]["alternates"] = ["NVDA"]
    with pytest.raises(PerpUniverseError, match="<dex>:<TICKER>"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_alternate_with_wrong_ticker(tmp_path):
    document = _base_document()
    document["companies"][0]["alternates"] = ["io:TSLA"]
    with pytest.raises(PerpUniverseError, match="does not match company ticker"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_empty_companies(tmp_path):
    document = _base_document()
    document["companies"] = []
    with pytest.raises(PerpUniverseError, match="non-empty"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_missing_file(tmp_path):
    with pytest.raises(PerpUniverseError, match="cannot read"):
        load_perp_universe(tmp_path / "absent.yaml")
