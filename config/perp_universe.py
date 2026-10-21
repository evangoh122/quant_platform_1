"""Typed loader and validator for ``config/perp_universe.yaml``.

Owner rule (2026-10-22): equity perpetuals are ingested **only** for the
companies listed in this file (the 78 qp1-universe single stocks with a
Hyperliquid HIP-3 perp) plus the Binance USD-M controls (BTCUSDT / ETHUSDT).
Nothing downstream may hard-code a perp symbol list; every ingestion job and
backfill reads this file through :func:`load_perp_universe`.

The loader is deliberately strict.  A typo in a provider symbol is a silent
data-loss bug (the exchange simply returns no candles), so the schema is
validated before any request is made:

* ``version`` is a positive integer;
* tickers are unique;
* ``symbol`` is exactly ``<dex>:<TICKER>`` and matches the entry's own
  ``ticker``/``dex`` (``xyz-NVDA`` is rejected);
* venues are limited to the implemented adapters (``hyperliquid`` for the
  equity perps, ``binance_usdm`` for the controls);
* HIP-3 dexes are limited to the three observed sub-dexes (``xyz``, ``para``,
  ``io``);
* the Binance controls must be present;
* unknown keys are rejected so a misspelled field cannot be ignored.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Tuple

import yaml

DEFAULT_PATH = Path(__file__).with_name("perp_universe.yaml")

#: Venues for which an ingestion adapter exists.
ALLOWED_VENUES: FrozenSet[str] = frozenset({"hyperliquid", "binance_usdm"})
#: HIP-3 sub-dexes observed in the Hyperliquid info API on 2026-10-21.
ALLOWED_DEXES: FrozenSet[str] = frozenset({"xyz", "para", "io"})
#: Liquidity buckets used only for review/reporting.
ALLOWED_TIERS: FrozenSet[str] = frozenset({"liquid", "medium", "thin"})
#: The owner requires both Binance controls in every probe and backfill.
REQUIRED_CONTROL_SYMBOLS: FrozenSet[str] = frozenset({"BTCUSDT", "ETHUSDT"})
#: Equity perpetuals are only implemented on Hyperliquid HIP-3.
EQUITY_VENUE = "hyperliquid"
CONTROL_VENUE = "binance_usdm"

_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9]{0,9}$")
_SYMBOL_RE = re.compile(r"^(?P<dex>[a-z0-9]+):(?P<ticker>[A-Z][A-Z0-9]{0,9})$")
_CONTROL_SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,20}$")

_ROOT_REQUIRED = frozenset({"version", "controls", "companies"})
_ROOT_OPTIONAL = frozenset({"selected_at", "selection"})
_CONTROL_KEYS = frozenset({"venue", "symbol"})
_COMPANY_REQUIRED = frozenset(
    {"ticker", "venue", "dex", "symbol", "tier"}
)
_COMPANY_OPTIONAL = frozenset({"vol_24h_usd", "oi_usd", "alternates"})


class PerpUniverseError(ValueError):
    """Raised when ``perp_universe.yaml`` violates the documented schema."""


@dataclass(frozen=True)
class PerpControl:
    """A market-wide weekend risk proxy (Binance USD-M perpetual)."""

    venue: str
    symbol: str


@dataclass(frozen=True)
class PerpCompany:
    """One equity perpetual in the owner-selected universe."""

    ticker: str
    venue: str
    dex: str
    symbol: str
    tier: str
    vol_24h_usd: Optional[float] = None
    oi_usd: Optional[float] = None
    alternates: Tuple[str, ...] = ()


@dataclass(frozen=True)
class PerpUniverse:
    """Validated view of ``config/perp_universe.yaml``."""

    version: int
    controls: Tuple[PerpControl, ...]
    companies: Tuple[PerpCompany, ...]
    selected_at: Optional[str]
    selection: Optional[str]
    path: Path

    @property
    def tickers(self) -> Tuple[str, ...]:
        """Equity tickers in file order (stable for reproducible requests)."""
        return tuple(c.ticker for c in self.companies)

    @property
    def instruments(self) -> Tuple[Tuple[str, str], ...]:
        """``(venue, provider_symbol)`` pairs: companies then controls."""
        return tuple(
            (c.venue, c.symbol) for c in self.companies
        ) + tuple((c.venue, c.symbol) for c in self.controls)

    @property
    def company_count(self) -> int:
        return len(self.companies)

    @property
    def control_count(self) -> int:
        return len(self.controls)

    def by_ticker(self) -> Dict[str, PerpCompany]:
        return {c.ticker: c for c in self.companies}

    def controls_by_symbol(self) -> Dict[str, PerpControl]:
        return {c.symbol: c for c in self.controls}


def _where(source: Path | str, key: str) -> str:
    return f"{source}: {key}"


def _require_mapping(value: Any, source: Path | str, key: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PerpUniverseError(
            f"{_where(source, key)} must be a mapping, got {type(value).__name__}"
        )
    return value


def _check_keys(
    raw: Mapping[str, Any],
    *,
    required: FrozenSet[str],
    optional: FrozenSet[str],
    source: Path | str,
    key: str,
) -> None:
    missing = required - set(raw)
    if missing:
        raise PerpUniverseError(
            f"{_where(source, key)} is missing required field(s): {sorted(missing)}"
        )
    unknown = set(raw) - required - optional
    if unknown:
        raise PerpUniverseError(
            f"{_where(source, key)} has unknown field(s): {sorted(unknown)}"
        )


def _as_int(value: Any, source: Path | str, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PerpUniverseError(
            f"{_where(source, key)} must be an integer, got {value!r}"
        )
    return value


def _as_number(value: Any, source: Path | str, key: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PerpUniverseError(
            f"{_where(source, key)} must be numeric, got {value!r}"
        )
    number = float(value)
    if number < 0:
        raise PerpUniverseError(
            f"{_where(source, key)} must be >= 0, got {value!r}"
        )
    return number


def _as_nonempty_str(value: Any, source: Path | str, key: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PerpUniverseError(
            f"{_where(source, key)} must be a non-empty string, got {value!r}"
        )
    return value.strip()


def _parse_control(raw: Any, source: Path | str, index: int) -> PerpControl:
    key = f"controls[{index}]"
    entry = _require_mapping(raw, source, key)
    _check_keys(entry, required=_CONTROL_KEYS, optional=frozenset(), source=source, key=key)
    venue = _as_nonempty_str(entry["venue"], source, f"{key}.venue")
    symbol = _as_nonempty_str(entry["symbol"], source, f"{key}.symbol")
    if venue not in ALLOWED_VENUES:
        raise PerpUniverseError(
            f"{_where(source, key + '.venue')} must be one of {sorted(ALLOWED_VENUES)}, "
            f"got {venue!r}"
        )
    if venue != CONTROL_VENUE:
        raise PerpUniverseError(
            f"{_where(source, key + '.venue')} must be {CONTROL_VENUE!r} for controls, "
            f"got {venue!r}"
        )
    if not _CONTROL_SYMBOL_RE.match(symbol):
        raise PerpUniverseError(
            f"{_where(source, key + '.symbol')} must be an uppercase Binance USD-M "
            f"symbol, got {symbol!r}"
        )
    return PerpControl(venue=venue, symbol=symbol)


def _parse_alternates(raw: Any, source: Path | str, key: str, ticker: str) -> Tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise PerpUniverseError(f"{_where(source, key)} must be a list, got {type(raw).__name__}")
    out: List[str] = []
    for position, item in enumerate(raw):
        item_key = f"{key}[{position}]"
        symbol = _as_nonempty_str(item, source, item_key)
        match = _SYMBOL_RE.match(symbol)
        if not match:
            raise PerpUniverseError(
                f"{_where(source, item_key)} must look like '<dex>:<TICKER>', got {symbol!r}"
            )
        if match.group("dex") not in ALLOWED_DEXES:
            raise PerpUniverseError(
                f"{_where(source, item_key)} uses dex {match.group('dex')!r}; "
                f"allowed: {sorted(ALLOWED_DEXES)}"
            )
        if match.group("ticker") != ticker:
            raise PerpUniverseError(
                f"{_where(source, item_key)} ticker {match.group('ticker')!r} does not "
                f"match company ticker {ticker!r}"
            )
        if symbol in out:
            raise PerpUniverseError(
                f"{_where(source, item_key)} duplicates alternate {symbol!r}"
            )
        out.append(symbol)
    return tuple(out)


def _parse_company(raw: Any, source: Path | str, index: int) -> PerpCompany:
    key = f"companies[{index}]"
    entry = _require_mapping(raw, source, key)
    _check_keys(
        entry,
        required=_COMPANY_REQUIRED,
        optional=_COMPANY_OPTIONAL,
        source=source,
        key=key,
    )
    ticker = _as_nonempty_str(entry["ticker"], source, f"{key}.ticker")
    if not _TICKER_RE.match(ticker):
        raise PerpUniverseError(
            f"{_where(source, key + '.ticker')} must be an uppercase ticker, got {ticker!r}"
        )
    venue = _as_nonempty_str(entry["venue"], source, f"{key}.venue")
    if venue not in ALLOWED_VENUES:
        raise PerpUniverseError(
            f"{_where(source, key + '.venue')} must be one of {sorted(ALLOWED_VENUES)}, "
            f"got {venue!r}"
        )
    if venue != EQUITY_VENUE:
        raise PerpUniverseError(
            f"{_where(source, key + '.venue')} must be {EQUITY_VENUE!r} for equity "
            f"perpetuals, got {venue!r}"
        )
    dex = _as_nonempty_str(entry["dex"], source, f"{key}.dex")
    if dex not in ALLOWED_DEXES:
        raise PerpUniverseError(
            f"{_where(source, key + '.dex')} must be one of {sorted(ALLOWED_DEXES)}, "
            f"got {dex!r}"
        )
    symbol = _as_nonempty_str(entry["symbol"], source, f"{key}.symbol")
    match = _SYMBOL_RE.match(symbol)
    if not match:
        raise PerpUniverseError(
            f"{_where(source, key + '.symbol')} must look like '<dex>:<TICKER>' "
            f"(for example {dex + ':' + ticker!r}), got {symbol!r}"
        )
    if match.group("dex") != dex:
        raise PerpUniverseError(
            f"{_where(source, key + '.symbol')} dex prefix {match.group('dex')!r} "
            f"does not match dex field {dex!r}"
        )
    if match.group("ticker") != ticker:
        raise PerpUniverseError(
            f"{_where(source, key + '.symbol')} ticker {match.group('ticker')!r} "
            f"does not match ticker field {ticker!r}"
        )
    tier = _as_nonempty_str(entry["tier"], source, f"{key}.tier")
    if tier not in ALLOWED_TIERS:
        raise PerpUniverseError(
            f"{_where(source, key + '.tier')} must be one of {sorted(ALLOWED_TIERS)}, "
            f"got {tier!r}"
        )
    return PerpCompany(
        ticker=ticker,
        venue=venue,
        dex=dex,
        symbol=symbol,
        tier=tier,
        vol_24h_usd=(
            _as_number(entry["vol_24h_usd"], source, f"{key}.vol_24h_usd")
            if "vol_24h_usd" in entry
            else None
        ),
        oi_usd=(
            _as_number(entry["oi_usd"], source, f"{key}.oi_usd")
            if "oi_usd" in entry
            else None
        ),
        alternates=_parse_alternates(entry.get("alternates"), source, f"{key}.alternates", ticker),
    )


def _parse_document(document: Any, source: Path | str) -> PerpUniverse:
    root = _require_mapping(document, source, "document")
    _check_keys(
        root,
        required=_ROOT_REQUIRED,
        optional=_ROOT_OPTIONAL,
        source=source,
        key="document",
    )

    version = _as_int(root["version"], source, "version")
    if version < 1:
        raise PerpUniverseError(f"{_where(source, 'version')} must be >= 1, got {version}")

    selected_at: Optional[str] = None
    if "selected_at" in root:
        selected_at = _as_nonempty_str(root["selected_at"], source, "selected_at")
        try:
            date.fromisoformat(selected_at)
        except ValueError as exc:
            raise PerpUniverseError(
                f"{_where(source, 'selected_at')} must be an ISO date (YYYY-MM-DD), "
                f"got {selected_at!r}"
            ) from exc

    selection: Optional[str] = None
    if "selection" in root:
        selection = _as_nonempty_str(root["selection"], source, "selection")

    raw_controls = root["controls"]
    if not isinstance(raw_controls, list) or not raw_controls:
        raise PerpUniverseError(
            f"{_where(source, 'controls')} must be a non-empty list; the Binance "
            f"controls {sorted(REQUIRED_CONTROL_SYMBOLS)} are mandatory"
        )
    controls = tuple(
        _parse_control(item, source, index) for index, item in enumerate(raw_controls)
    )
    control_symbols = [c.symbol for c in controls]
    duplicates = {s for s in control_symbols if control_symbols.count(s) > 1}
    if duplicates:
        raise PerpUniverseError(
            f"{_where(source, 'controls')} has duplicate symbol(s): {sorted(duplicates)}"
        )
    missing_controls = REQUIRED_CONTROL_SYMBOLS - set(control_symbols)
    if missing_controls:
        raise PerpUniverseError(
            f"{_where(source, 'controls')} is missing required control(s): "
            f"{sorted(missing_controls)}"
        )

    raw_companies = root["companies"]
    if not isinstance(raw_companies, list) or not raw_companies:
        raise PerpUniverseError(
            f"{_where(source, 'companies')} must be a non-empty list"
        )
    companies = tuple(
        _parse_company(item, source, index) for index, item in enumerate(raw_companies)
    )

    seen_tickers: Dict[str, int] = {}
    seen_symbols: Dict[str, int] = {}
    for index, company in enumerate(companies):
        if company.ticker in seen_tickers:
            raise PerpUniverseError(
                f"{_where(source, 'companies')} has duplicate ticker {company.ticker!r} "
                f"at indexes {seen_tickers[company.ticker]} and {index}"
            )
        seen_tickers[company.ticker] = index
        if company.symbol in seen_symbols:
            raise PerpUniverseError(
                f"{_where(source, 'companies')} has duplicate provider symbol "
                f"{company.symbol!r} at indexes {seen_symbols[company.symbol]} and {index}"
            )
        seen_symbols[company.symbol] = index

    overlap = set(seen_tickers) & set(control_symbols)
    if overlap:
        raise PerpUniverseError(
            f"{_where(source, 'document')} uses ticker(s) both as company and control: "
            f"{sorted(overlap)}"
        )

    return PerpUniverse(
        version=version,
        controls=controls,
        companies=companies,
        selected_at=selected_at,
        selection=selection,
        path=Path(source),
    )


def load_perp_universe(path: str | Path | None = None) -> PerpUniverse:
    """Load and validate the perp universe.

    Parameters
    ----------
    path:
        YAML file to read.  Defaults to the ``PERP_UNIVERSE_YAML`` environment
        variable when set, otherwise ``config/perp_universe.yaml`` beside this
        module.
    """
    if path is None:
        configured = os.getenv("PERP_UNIVERSE_YAML")
        resolved = Path(configured) if configured else DEFAULT_PATH
    else:
        resolved = Path(path)

    try:
        text = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        raise PerpUniverseError(
            f"cannot read perp universe at {resolved}: {exc.strerror or exc}"
        ) from exc

    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PerpUniverseError(f"{resolved}: invalid YAML: {exc}") from exc
    return _parse_document(document, resolved)


if __name__ == "__main__":
    universe = load_perp_universe()
    print(
        f"perp universe v{universe.version}: {universe.company_count} companies, "
        f"{universe.control_count} controls ({universe.path})"
    )
    print("controls:", ", ".join(f"{c.venue}:{c.symbol}" for c in universe.controls))
    print("tickers:", ", ".join(universe.tickers))
