"""Tests for the typed perp-universe loader (config/perp_universe.py).

Expectations are derived from the production loader and the checked-in
configuration; no validation logic is re-implemented here.
"""
from __future__ import annotations

import copy
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

from config.data_sources import DATA_SOURCES, validate_data_source
from config.perp_universe import (
    ALLOWED_TIERS,
    ALLOWED_UNDERLYING_TYPES,
    CONTROL_VENUE,
    EQUITY_VENUE,
    INSTRUMENT_TYPE,
    VENUE_DATA_SOURCES,
    PerpUniverseError,
    data_source_for_venue,
    derive_flags,
    load_perp_universe,
    tier_for_weekend_usd_per_h,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REAL_CONFIG = _REPO_ROOT / "config" / "perp_universe.yaml"


def _base_document():
    return yaml.safe_load(_REAL_CONFIG.read_text(encoding="utf-8"))


def _write_document(tmp_path: Path, document) -> Path:
    target = tmp_path / "perp_universe.yaml"
    target.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return target


def test_real_file_loads_v4_universe():
    universe = load_perp_universe(_REAL_CONFIG)
    assert universe.version == 4
    assert universe.company_count == 78
    assert universe.commodity_count == 8
    assert universe.control_count == 2
    assert universe.path == _REAL_CONFIG
    assert [control.symbol for control in universe.controls] == [
        "BTCUSDT",
        "ETHUSDT",
    ]
    assert len(set(universe.tickers)) == 78
    assert len(universe.instruments) == 88
    assert universe.instrument_defaults["instrument_type"] == INSTRUMENT_TYPE
    assert universe.instrument_defaults["is_equity"] is False
    assert universe.instrument_defaults["is_derivative"] is True
    assert universe.instrument_defaults["contract"] == "linear_perpetual"
    for company in universe.companies:
        assert company.venue == EQUITY_VENUE
        assert company.instrument_type == INSTRUMENT_TYPE
        assert company.underlying_type in ALLOWED_UNDERLYING_TYPES
        assert company.underlying == company.ticker
        assert company.tier in ALLOWED_TIERS
        assert company.symbol == f"{company.dex}:{company.ticker}"
        assert company.weekend_usd_per_h >= 0
        assert 0 <= company.zero_volume_weekend_share <= 1


def test_derivative_underlying_labels_for_round_one_suspects():
    universe = load_perp_universe(_REAL_CONFIG)
    labels = {c.ticker: c.underlying_type for c in universe.companies}
    assert labels["BOT"] == "fund"
    assert labels["STRC"] == "preferred"
    assert labels["KSTR"] == "etf"
    # All three stay in the universe: the owner chose all 78.
    assert {"BOT", "STRC", "KSTR"} <= set(universe.tickers)


def test_commodity_perps_are_paired_with_etfs():
    universe = load_perp_universe(_REAL_CONFIG)
    assert {c.commodity for c in universe.commodities} == {
        "wti_crude",
        "brent_crude",
        "silver",
        "gold",
        "natural_gas",
        "copper",
        "platinum",
        "palladium",
    }
    for commodity in universe.commodities:
        assert commodity.instrument_type == INSTRUMENT_TYPE
        assert commodity.underlying_type == "commodity"
        assert commodity.venue == EQUITY_VENUE
        assert commodity.etfs
        assert commodity.etf_kind in {"physical", "futures"}
        assert commodity.tier in ALLOWED_TIERS


def test_controls_are_binance_usdm_crypto_perps():
    universe = load_perp_universe(_REAL_CONFIG)
    assert {control.venue for control in universe.controls} == {CONTROL_VENUE}
    for control in universe.controls:
        assert control.instrument_type == INSTRUMENT_TYPE
        assert control.underlying_type == "crypto"


def test_instruments_include_companies_commodities_then_controls():
    universe = load_perp_universe(_REAL_CONFIG)
    instruments = universe.instruments
    assert len(instruments) == 80 + universe.commodity_count
    assert instruments[0] == (
        universe.companies[0].venue,
        universe.companies[0].symbol,
    )
    assert instruments[-1] == (CONTROL_VENUE, "ETHUSDT")
    assert ("hyperliquid", "xyz:GOLD") in instruments


def test_tier_thresholds():
    assert tier_for_weekend_usd_per_h(250_000) == "A"
    assert tier_for_weekend_usd_per_h(249_999.99) == "B"
    assert tier_for_weekend_usd_per_h(50_000) == "B"
    assert tier_for_weekend_usd_per_h(49_999.99) == "C"
    assert tier_for_weekend_usd_per_h(10_000) == "C"
    assert tier_for_weekend_usd_per_h(9_999.99) == "D"
    assert tier_for_weekend_usd_per_h(0) == "D"
    with pytest.raises(PerpUniverseError, match=">= 0"):
        tier_for_weekend_usd_per_h(-1)


def test_flag_rules():
    from datetime import date

    start = date(2026, 8, 26)
    assert derive_flags(date(2026, 8, 26), 0.0, start) == ()
    assert derive_flags(date(2026, 9, 1), 0.0, start) == ("new",)
    assert derive_flags(date(2026, 8, 26), 0.25, start) == ()
    assert derive_flags(date(2026, 8, 26), 0.2501, start) == ("sparse",)
    assert derive_flags(date(2026, 9, 1), 0.9, start) == ("new", "sparse")


def test_env_override_is_honoured(tmp_path, monkeypatch):
    target = _write_document(tmp_path, _base_document())
    monkeypatch.setenv("PERP_UNIVERSE_YAML", str(target))
    universe = load_perp_universe()
    assert universe.company_count == 78
    assert universe.path == target


def test_rejects_missing_instrument_type(tmp_path):
    document = _base_document()
    del document["companies"][0]["instrument_type"]
    with pytest.raises(PerpUniverseError, match="instrument_type"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_non_perpetual_instrument_type(tmp_path):
    # Mutation target: a loader that accepts instrument_type=equity must fail
    # this test.  Perps are derivatives, never the underlying equity.
    document = _base_document()
    document["companies"][0]["instrument_type"] = "equity"
    with pytest.raises(PerpUniverseError, match="perpetual_future"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_non_perpetual_commodity_instrument_type(tmp_path):
    document = _base_document()
    document["commodities"][0]["instrument_type"] = "spot"
    with pytest.raises(PerpUniverseError, match="perpetual_future"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_non_perpetual_control_instrument_type(tmp_path):
    document = _base_document()
    del document["controls"][0]["instrument_type"]
    with pytest.raises(PerpUniverseError, match="instrument_type"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_unknown_underlying_type(tmp_path):
    document = _base_document()
    document["companies"][0]["underlying_type"] = "stock"
    with pytest.raises(PerpUniverseError, match="underlying_type"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_missing_underlying_type(tmp_path):
    document = _base_document()
    del document["companies"][0]["underlying_type"]
    with pytest.raises(PerpUniverseError, match="underlying_type"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_commodity_underlying_type_in_company_section(tmp_path):
    document = _base_document()
    document["companies"][0]["underlying_type"] = "commodity"
    with pytest.raises(PerpUniverseError, match="underlying_type"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_duplicate_ticker(tmp_path):
    document = _base_document()
    duplicate = document["companies"][0]
    target = document["companies"][1]
    target["ticker"] = duplicate["ticker"]
    target["underlying"] = duplicate["ticker"]
    target["symbol"] = f"{target['dex']}:{duplicate['ticker']}"
    with pytest.raises(PerpUniverseError, match="duplicate ticker"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_duplicate_commodity_provider_symbol(tmp_path):
    document = _base_document()
    document["commodities"][1]["symbol"] = document["commodities"][0]["symbol"]
    document["commodities"][1]["dex"] = document["commodities"][0]["dex"]
    with pytest.raises(PerpUniverseError, match="duplicates"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_commodity_without_etfs(tmp_path):
    document = _base_document()
    del document["commodities"][0]["etfs"]
    with pytest.raises(PerpUniverseError, match="etfs"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_empty_etf_list(tmp_path):
    document = _base_document()
    document["commodities"][0]["etfs"] = []
    with pytest.raises(PerpUniverseError, match="etfs"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_unknown_etf_kind(tmp_path):
    document = _base_document()
    document["commodities"][0]["etf_kind"] = "leveraged"
    with pytest.raises(PerpUniverseError, match="etf_kind"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_tier_inconsistent_with_measurement(tmp_path):
    document = _base_document()
    assert document["companies"][0]["tier"] == "A"
    document["companies"][0]["tier"] = "B"
    with pytest.raises(PerpUniverseError, match="weekend_usd_per_h"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_flags_inconsistent_with_measurement(tmp_path):
    document = _base_document()
    nvda = next(c for c in document["companies"] if c["ticker"] == "NVDA")
    assert nvda["flags"] == []
    nvda["flags"] = ["sparse"]
    with pytest.raises(PerpUniverseError, match="flags"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_unknown_flag(tmp_path):
    document = _base_document()
    nvda = next(c for c in document["companies"] if c["ticker"] == "NVDA")
    nvda["flags"] = ["illiquid"]
    with pytest.raises(PerpUniverseError, match="must be one of"):
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
    document["controls"] = [
        {
            "instrument_type": "perpetual_future",
            "underlying_type": "crypto",
            "underlying": "BTC",
            "venue": "binance_usdm",
            "data_source": "binance_um",
            "symbol": "BTCUSDT",
        }
    ]
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


@pytest.mark.parametrize("version", [0, 3, 5])
def test_rejects_bad_version(tmp_path, version):
    # The loader validates one schema; a stale or future version is rejected
    # rather than silently reinterpreted.
    document = _base_document()
    document["version"] = version
    with pytest.raises(PerpUniverseError, match="must be 4"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_commodity_tier_inconsistent_with_measurement(tmp_path):
    # Mutation target: deleting the commodity tier/weekend_usd_per_h check must
    # fail here (companies already had this test; commodities did not).
    document = _base_document()
    assert document["commodities"][0]["tier"] == "A"
    document["commodities"][0]["tier"] = "B"
    with pytest.raises(PerpUniverseError, match="weekend_usd_per_h"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_commodity_first_bar_after_the_window(tmp_path):
    # Same bound as company rows: a first bar after the measurement window end
    # means the row's liquidity was never measured.
    document = _base_document()
    window_end = date.fromisoformat(document["liquidity_window"]["end"])
    document["commodities"][0]["first_bar"] = (
        window_end + timedelta(days=1)
    ).isoformat()
    with pytest.raises(PerpUniverseError, match="after the measurement window end"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_missing_instrument_defaults(tmp_path):
    document = _base_document()
    del document["instrument_defaults"]
    with pytest.raises(PerpUniverseError, match="instrument_defaults"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_is_equity_true(tmp_path):
    document = _base_document()
    document["instrument_defaults"]["is_equity"] = True
    with pytest.raises(PerpUniverseError, match="is_equity"):
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
    document["companies"][0]["weekend_usd_per_h"] = -1
    with pytest.raises(PerpUniverseError, match=">= 0"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_zero_volume_share_above_one(tmp_path):
    document = _base_document()
    document["companies"][0]["zero_volume_weekend_share"] = 1.5
    with pytest.raises(PerpUniverseError, match=r"\[0, 1\]"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_malformed_alternate(tmp_path):
    document = _base_document()
    document["companies"][0]["alternates"] = ["NVDA"]
    with pytest.raises(PerpUniverseError, match="<dex>:<TICKER>"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_empty_companies(tmp_path):
    document = _base_document()
    document["companies"] = []
    with pytest.raises(PerpUniverseError, match="non-empty"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_missing_file(tmp_path):
    with pytest.raises(PerpUniverseError, match="cannot read"):
        load_perp_universe(tmp_path / "absent.yaml")


# ---------------------------------------------------------------------------
# data_source (owner rule 2026-10-22: one provider code on every row)
# ---------------------------------------------------------------------------


def test_every_real_row_carries_a_valid_data_source():
    universe = load_perp_universe(_REAL_CONFIG)
    rows = (*universe.companies, *universe.commodities, *universe.controls)
    assert len(rows) == 78 + 8 + 2
    for row in rows:
        assert row.data_source in DATA_SOURCES
        assert validate_data_source(row.data_source) == row.data_source
        # The code must be the one the row's venue implies.
        assert row.data_source == data_source_for_venue(row.venue)


def test_real_rows_use_the_venue_provider_codes():
    universe = load_perp_universe(_REAL_CONFIG)
    assert {company.data_source for company in universe.companies} == {"hyperliquid"}
    assert {commodity.data_source for commodity in universe.commodities} == {
        "hyperliquid"
    }
    # The repository venue is binance_usdm; the owner-rule provider code is binance_um.
    assert {control.data_source for control in universe.controls} == {"binance_um"}
    assert VENUE_DATA_SOURCES["binance_usdm"] == "binance_um"


def test_data_source_for_venue_rejects_an_unmapped_venue():
    with pytest.raises(PerpUniverseError, match="no data_source mapping"):
        data_source_for_venue("kraken")


@pytest.mark.parametrize("section", ["companies", "commodities", "controls"])
def test_rejects_missing_data_source(tmp_path, section):
    # Mutation target: a loader that defaults the code must fail this test.
    document = _base_document()
    del document[section][0]["data_source"]
    with pytest.raises(PerpUniverseError, match="data_source"):
        load_perp_universe(_write_document(tmp_path, document))


@pytest.mark.parametrize("section", ["companies", "commodities", "controls"])
@pytest.mark.parametrize("bad", ["polygon", "Massive", "binance_usdm", "", None, 1])
def test_rejects_unknown_or_malformed_data_source(tmp_path, section, bad):
    document = _base_document()
    document[section][0]["data_source"] = bad
    with pytest.raises(PerpUniverseError, match="data_source"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_company_venue_data_source_mismatch(tmp_path):
    # A Hyperliquid perp labelled binance_um is a lineage lie, not a near miss.
    document = _base_document()
    document["companies"][0]["data_source"] = "binance_um"
    with pytest.raises(PerpUniverseError, match="must be 'hyperliquid' for venue"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_commodity_venue_data_source_mismatch(tmp_path):
    document = _base_document()
    document["commodities"][0]["data_source"] = "binance_um"
    with pytest.raises(PerpUniverseError, match="must be 'hyperliquid' for venue"):
        load_perp_universe(_write_document(tmp_path, document))


def test_rejects_control_venue_data_source_mismatch(tmp_path):
    document = _base_document()
    document["controls"][0]["data_source"] = "hyperliquid"
    with pytest.raises(PerpUniverseError, match="must be 'binance_um' for venue"):
        load_perp_universe(_write_document(tmp_path, document))
