"""tests/test_research_symbols.py — research/benchmark symbol group config.

Owner decision 2026-10-22 (option D of
``.agents/requests/SOL-commodity-etfs-advice.txt``): commodity ETFs get daily
research coverage (split-adjusted silver + corporate actions) WITHOUT entering
the trading universe or the published baseline signals.

These tests pin the loader contract of ``config/research_symbols.py``:
config-order symbols, unique upper-case tickers, per-symbol ``commodity`` and
``etf_kind``, and an overlap with the trading universe reported as a warning
rather than an error.
"""
from __future__ import annotations

import textwrap
import warnings
from pathlib import Path

import pytest

from config.research_symbols import (
    DEFAULT_GROUP,
    ETF_KINDS,
    load_research_registry,
    load_research_symbols,
    normalize_symbol,
)
from config.universe import load_universe

_REPO_ROOT = Path(__file__).resolve().parent.parent

# The owner-named commodity ETF group (BUILD-research-symbols.md). Order is the
# configuration order; the loader must preserve it.
EXPECTED_SYMBOLS = [
    "GLD", "IAU", "SLV", "SIVR", "USO",
    "BNO", "UNG", "CPER", "PPLT", "PALL",
]

# Physical vs futures-backed: futures ETFs carry roll yield, which matters for
# the weekend-gap research (contango is not a spot move).
EXPECTED_ETF_KIND = {
    "GLD": "physical",
    "IAU": "physical",
    "SLV": "physical",
    "SIVR": "physical",
    "USO": "futures",
    "BNO": "futures",
    "UNG": "futures",
    "CPER": "futures",
    "PPLT": "physical",
    "PALL": "physical",
}

_VALID_META = """
      {symbol}:
        commodity: gold
        etf_kind: physical
"""


def _write(tmp_path: Path, body: str) -> str:
    path = tmp_path / "research_symbols.yaml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return str(path)


def _config(symbols_yaml: str) -> str:
    """Wrap a ``symbols:`` mapping (already indented by 6 spaces) in a config."""
    return (
        "groups:\n"
        f"  {DEFAULT_GROUP}:\n"
        "    symbols:\n"
        f"{symbols_yaml}"
    )


class TestDefaultConfiguration:
    def test_default_group_lists_the_ten_commodity_etfs_in_order(self):
        assert load_research_symbols() == EXPECTED_SYMBOLS

    def test_default_group_group_name(self):
        assert DEFAULT_GROUP == "commodity_etfs"

    def test_every_symbol_declares_commodity_and_etf_kind(self):
        registry = load_research_registry()
        assert list(registry) == EXPECTED_SYMBOLS
        for symbol, meta in registry.items():
            assert meta["commodity"], f"{symbol} has no commodity"
            assert meta["etf_kind"] in ETF_KINDS

    def test_etf_kind_matches_the_instrument(self):
        registry = load_research_registry()
        assert {s: m["etf_kind"] for s, m in registry.items()} == EXPECTED_ETF_KIND

    def test_group_is_disjoint_from_the_trading_universe(self):
        overlap = set(load_research_symbols()) & {s.upper() for s in load_universe()}
        assert not overlap, (
            f"research symbols must not be in config/universe.yaml: {sorted(overlap)}"
        )

    def test_disjoint_group_emits_no_overlap_warning(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            load_research_symbols()
        assert not [w for w in caught if "trading universe" in str(w.message)]

    def test_loader_imports_no_pandas_or_duckdb(self):
        """Acceptance: research config code must stay free of pandas/DuckDB."""
        source = (_REPO_ROOT / "config" / "research_symbols.py").read_text(
            encoding="utf-8"
        )
        for banned in ("import pandas", "import duckdb", "from pandas", "from duckdb"):
            assert banned not in source, f"config/research_symbols.py uses {banned!r}"


class TestValidation:
    def test_duplicate_symbol_rejected(self, tmp_path):
        body = _config(
            "      GLD:\n        commodity: gold\n        etf_kind: physical\n"
            "      GLD:\n        commodity: silver\n        etf_kind: futures\n"
        )
        path = _write(tmp_path, body)
        with pytest.raises(ValueError, match="duplicate"):
            load_research_symbols(path=path)

    def test_lowercase_symbol_rejected(self, tmp_path):
        path = _write(tmp_path, _config(_VALID_META.format(symbol="gld")))
        with pytest.raises(ValueError, match="upper-case"):
            load_research_symbols(path=path)

    def test_non_ticker_symbol_rejected(self, tmp_path):
        # A quoted apostrophe would break out of the quoted SQL literal used by
        # the corporate-action universe screen.
        path = _write(
            tmp_path,
            _config(
                "      \"GLD'DROP\":\n        commodity: gold\n"
                "        etf_kind: physical\n"
            ),
        )
        with pytest.raises(ValueError, match="invalid research symbol"):
            load_research_symbols(path=path)

    def test_non_string_symbol_key_rejected(self, tmp_path):
        # Unquoted `ON` parses as the YAML boolean True, not the string "ON".
        path = _write(tmp_path, _config(_VALID_META.format(symbol="ON")))
        with pytest.raises(ValueError, match="must be a string"):
            load_research_symbols(path=path)

    def test_missing_commodity_rejected(self, tmp_path):
        path = _write(
            tmp_path,
            _config("      GLD:\n        etf_kind: physical\n"),
        )
        with pytest.raises(ValueError, match="missing 'commodity'"):
            load_research_symbols(path=path)

    def test_unknown_etf_kind_rejected(self, tmp_path):
        path = _write(
            tmp_path,
            _config("      GLD:\n        commodity: gold\n        etf_kind: swap\n"),
        )
        with pytest.raises(ValueError, match="etf_kind"):
            load_research_symbols(path=path)

    def test_metadata_mapping_required(self, tmp_path):
        path = _write(tmp_path, _config("      GLD: physical\n"))
        with pytest.raises(ValueError, match="metadata mapping"):
            load_research_symbols(path=path)

    def test_empty_group_rejected(self, tmp_path):
        path = _write(tmp_path, "groups:\n  commodity_etfs:\n    symbols: {}\n")
        with pytest.raises(ValueError, match="non-empty 'symbols'"):
            load_research_symbols(path=path)

    def test_unknown_group_rejected(self, tmp_path):
        path = _write(tmp_path, _config(_VALID_META.format(symbol="GLD")))
        with pytest.raises(ValueError, match="missing research group"):
            load_research_symbols(path=path, group="not_a_group")

    def test_missing_groups_mapping_rejected(self, tmp_path):
        path = _write(tmp_path, "symbols:\n  - \"GLD\"\n")
        with pytest.raises(ValueError, match="top-level 'groups'"):
            load_research_symbols(path=path)


class TestTradingUniverseOverlap:
    """Overlap is a warning, not an error (a staged promotion stays runnable)."""

    def test_overlap_warns_but_still_returns_symbols(self, tmp_path):
        trading_symbol = load_universe()[0]  # read, not hardcoded
        body = _config(
            "      GLD:\n        commodity: gold\n        etf_kind: physical\n"
            f"      {trading_symbol}:\n        commodity: gold\n"
            "        etf_kind: physical\n"
        )
        path = _write(tmp_path, body)
        with pytest.warns(UserWarning, match="trading universe") as record:
            symbols = load_research_symbols(path=path)
        assert symbols == ["GLD", trading_symbol]
        assert trading_symbol in str(record[0].message)

    def test_overlap_is_not_a_duplicate_error(self, tmp_path):
        trading_symbol = load_universe()[0]
        body = _config(
            f"      {trading_symbol}:\n        commodity: gold\n"
            "        etf_kind: physical\n"
        )
        path = _write(tmp_path, body)
        with pytest.warns(UserWarning, match="trading universe"):
            assert load_research_symbols(path=path) == [trading_symbol]


class TestNormalizeSymbol:
    def test_accepts_plain_and_share_class_tickers(self):
        assert normalize_symbol("GLD") == "GLD"
        assert normalize_symbol("BRK.B") == "BRK.B"
        assert normalize_symbol("BF-B") == "BF-B"

    @pytest.mark.parametrize("bad", ["gld", "GLD'; --", "GLD DROP", "", 7, None])
    def test_rejects_anything_that_is_not_an_upper_case_ticker(self, bad):
        with pytest.raises(ValueError):
            normalize_symbol(bad)
