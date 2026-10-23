"""Typed loader and validator for ``config/perp_universe.yaml`` (version 4).

Owner rule (2026-10-22): the instruments ingested for weekend research are
**perpetual futures** — derivatives traded on crypto venues — never the equity,
ETF, fund, preferred or spot commodity they track.  The file therefore carries
``instrument_type: perpetual_future`` on every row plus an ``underlying_type``
(``equity`` / ``etf`` / ``fund`` / ``preferred`` / ``commodity`` / ``crypto``)
and the ``underlying`` it tracks through the venue's oracle.

Universe (owner choices):

* 78 company perpetuals on Hyperliquid HIP-3 (the qp1-universe single stocks);
* 8 commodity perpetuals paired with Massive ETFs (``etf_kind`` physical or
  futures);
* the mandatory Binance USD-M ``BTCUSDT`` / ``ETHUSDT`` controls.

Liquidity is measured **while NYSE is closed** from 1h candles.  Tiers are
derived from ``weekend_usd_per_h``: ``A >= 250k``, ``B >= 50k``, ``C >= 10k``,
``D < 10k``.  Flags are derived too: ``new`` = first bar after the measurement
window start (short history) and ``sparse`` = more than 25% of expected weekend
hours with zero volume.

Tiers and flags are **descriptive stratification only**.  The checked-in values
were measured over 2026-08-26..2026-10-21, i.e. *after* most weekends in the
study, so using them as a model input is look-ahead.  Any model input or filter
must use trailing point-in-time liquidity computed only from data strictly
before each window start; the static values are for reporting and universe
description.  They are never ingestion filters.

The loader is deliberately strict.  A typo in a provider symbol is a silent
data-loss bug (the exchange simply returns no candles), so the schema is
validated before any request is made:

* ``version`` is exactly 4 (the schema this loader validates); any other value
  is rejected so a stale file cannot be read with new semantics;
* every row has ``instrument_type: perpetual_future``; anything else (including
  a missing value) is rejected;
* ``underlying_type`` is one of the documented values and is consistent with
  the section (companies cannot be ``commodity``; controls must be ``crypto``);
* tickers, provider symbols and commodity names are unique;
* ``symbol`` is exactly ``<dex>:<TICKER>`` and matches the entry's own
  ``ticker``/``dex`` (``xyz-NVDA`` is rejected);
* company and commodity tiers agree with the measured ``weekend_usd_per_h`` and
  the stored ``flags`` agree with the measured history;
* commodity rows must carry a non-empty ``etfs`` list and a valid ``etf_kind``;
* ``first_bar`` on companies and commodities must fall inside the measurement
  window (a first bar after ``window.end`` was never measured);
* venues are limited to the implemented adapters; HIP-3 dexes are limited to
  the three observed sub-dexes (``xyz``, ``para``, ``io``);
* every row carries an explicit ``data_source`` from :mod:`config.data_sources`
  (one provider code); a missing/unknown code, or one that contradicts the
  row's venue (``hyperliquid -> hyperliquid``, ``binance_usdm -> binance_um``),
  is rejected;
* the Binance controls must be present;
* unknown keys are rejected so a misspelled field cannot be ignored.

Nothing downstream may hard-code a perp symbol list; every ingestion job and
backfill reads this file through :func:`load_perp_universe`.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple

import yaml

from config.data_sources import DATA_SOURCES, validate_data_source

DEFAULT_PATH = Path(__file__).with_name("perp_universe.yaml")

#: Every instrument in this track is a perpetual future (a derivative).
INSTRUMENT_TYPE = "perpetual_future"
#: Contract style recorded in ``instrument_defaults``.
CONTRACT_TYPE = "linear_perpetual"

#: Venues for which an ingestion adapter exists.
ALLOWED_VENUES: FrozenSet[str] = frozenset({"hyperliquid", "binance_usdm"})
#: HIP-3 sub-dexes observed in the Hyperliquid info API on 2026-10-21.
ALLOWED_DEXES: FrozenSet[str] = frozenset({"xyz", "para", "io"})
#: Closed-market liquidity tiers (A most liquid).
ALLOWED_TIERS: FrozenSet[str] = frozenset({"A", "B", "C", "D"})
#: Underlying classifications permitted anywhere in the file.
ALLOWED_UNDERLYING_TYPES: FrozenSet[str] = frozenset(
    {"equity", "etf", "fund", "preferred", "commodity", "crypto"}
)
#: Company rows track listed securities or funds, never commodities/crypto.
COMPANY_UNDERLYING_TYPES: FrozenSet[str] = frozenset(
    {"equity", "etf", "fund", "preferred"}
)
#: Commodity rows track spot commodities.
COMMODITY_UNDERLYING_TYPES: FrozenSet[str] = frozenset({"commodity"})
#: Binance controls are crypto perpetuals.
CONTROL_UNDERLYING_TYPES: FrozenSet[str] = frozenset({"crypto"})
#: Review flags derived from the liquidity measurement.
ALLOWED_FLAGS: FrozenSet[str] = frozenset({"new", "sparse"})
#: ETF wrapper types for commodity perps.
ALLOWED_ETF_KINDS: FrozenSet[str] = frozenset({"physical", "futures"})
#: Lower bound (USD per hour) for each tier above D, highest first.
TIER_THRESHOLDS: Tuple[Tuple[str, float], ...] = (
    ("A", 250_000.0),
    ("B", 50_000.0),
    ("C", 10_000.0),
)
#: A weekend is "sparse" above this share of zero-volume hours.
SPARSE_ZERO_VOLUME_SHARE = 0.25

#: The owner requires both Binance controls in every probe and backfill.
REQUIRED_CONTROL_SYMBOLS: FrozenSet[str] = frozenset({"BTCUSDT", "ETHUSDT"})
#: Equity and commodity perpetuals are only implemented on Hyperliquid HIP-3.
EQUITY_VENUE = "hyperliquid"
CONTROL_VENUE = "binance_usdm"
#: ``data_source`` code implied by each implemented venue.  ``binance_usdm`` is
#: this repository's venue name for Binance USD-M futures, whose owner-rule
#: provider code is ``binance_um``.
VENUE_DATA_SOURCES: Mapping[str, str] = {
    "hyperliquid": "hyperliquid",
    "binance_usdm": "binance_um",
    "binance_um": "binance_um",
}

_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9]{0,9}$")
_SYMBOL_RE = re.compile(r"^(?P<dex>[a-z0-9]+):(?P<ticker>[A-Z][A-Z0-9]{0,9})$")
_CONTROL_SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,20}$")
_COMMODITY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_ETF_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.]{0,9}$")

_ROOT_REQUIRED = frozenset(
    {"version", "instrument_defaults", "liquidity_window", "controls", "companies"}
)
_ROOT_OPTIONAL = frozenset({"commodities", "selected_at", "selection"})
_DEFAULTS_REQUIRED = frozenset(
    {"instrument_type", "is_equity", "is_derivative", "contract"}
)
_DEFAULTS_OPTIONAL = frozenset({"quote_currency", "trades_24x7"})
_WINDOW_REQUIRED = frozenset({"start", "end", "basis"})
_CONTROL_REQUIRED = frozenset(
    {
        "instrument_type",
        "underlying_type",
        "underlying",
        "venue",
        "data_source",
        "symbol",
    }
)
_CONTROL_OPTIONAL = frozenset({"quote_currency"})
_COMPANY_REQUIRED = frozenset(
    {
        "ticker",
        "instrument_type",
        "underlying_type",
        "underlying",
        "venue",
        "data_source",
        "dex",
        "symbol",
        "tier",
        "weekend_usd_per_h",
        "closed_usd_per_h",
        "zero_volume_weekend_share",
        "first_bar",
        "flags",
    }
)
_COMPANY_OPTIONAL = frozenset({"quote_currency", "alternates"})
_COMMODITY_REQUIRED = frozenset(
    {
        "commodity",
        "instrument_type",
        "underlying_type",
        "venue",
        "data_source",
        "dex",
        "symbol",
        "etfs",
        "etf_kind",
        "tier",
        "weekend_usd_per_h",
        "zero_volume_weekend_share",
        "first_bar",
    }
)
_COMMODITY_OPTIONAL = frozenset({"quote_currency"})


class PerpUniverseError(ValueError):
    """Raised when ``perp_universe.yaml`` violates the documented schema."""


@dataclass(frozen=True)
class PerpLiquidityWindow:
    """Measurement window for the closed-market liquidity numbers."""

    start: date
    end: date
    basis: str


@dataclass(frozen=True)
class PerpControl:
    """A market-wide weekend risk proxy (Binance USD-M crypto perpetual)."""

    venue: str
    data_source: str
    symbol: str
    instrument_type: str
    underlying_type: str
    underlying: str
    quote_currency: Optional[str] = None


@dataclass(frozen=True)
class PerpCompany:
    """One company perpetual in the owner-selected universe."""

    ticker: str
    instrument_type: str
    underlying_type: str
    underlying: str
    venue: str
    data_source: str
    dex: str
    symbol: str
    tier: str
    weekend_usd_per_h: float
    closed_usd_per_h: float
    zero_volume_weekend_share: float
    first_bar: date
    flags: Tuple[str, ...] = ()
    quote_currency: Optional[str] = None
    alternates: Tuple[str, ...] = ()


@dataclass(frozen=True)
class PerpCommodity:
    """One commodity perpetual paired with a Massive ETF wrapper."""

    commodity: str
    instrument_type: str
    underlying_type: str
    venue: str
    data_source: str
    dex: str
    symbol: str
    etfs: Tuple[str, ...]
    etf_kind: str
    tier: str
    weekend_usd_per_h: float
    zero_volume_weekend_share: float
    first_bar: date
    flags: Tuple[str, ...] = ()
    quote_currency: Optional[str] = None


@dataclass(frozen=True)
class PerpUniverse:
    """Validated view of ``config/perp_universe.yaml``."""

    version: int
    instrument_defaults: Mapping[str, Any]
    liquidity_window: PerpLiquidityWindow
    controls: Tuple[PerpControl, ...]
    companies: Tuple[PerpCompany, ...]
    commodities: Tuple[PerpCommodity, ...]
    selected_at: Optional[str]
    selection: Optional[str]
    path: Path

    @property
    def tickers(self) -> Tuple[str, ...]:
        """Equity/fund tickers in file order (stable for reproducible requests)."""
        return tuple(c.ticker for c in self.companies)

    @property
    def commodity_symbols(self) -> Tuple[str, ...]:
        return tuple(c.symbol for c in self.commodities)

    @property
    def all_symbols(self) -> Tuple[str, ...]:
        """Provider symbols: companies, then commodities, then controls."""
        return tuple(c.symbol for c in self.companies) + tuple(
            c.symbol for c in self.commodities
        ) + tuple(c.symbol for c in self.controls)

    @property
    def instruments(self) -> Tuple[Tuple[str, str], ...]:
        """``(venue, provider_symbol)`` pairs: companies, commodities, controls."""
        return (
            tuple((c.venue, c.symbol) for c in self.companies)
            + tuple((c.venue, c.symbol) for c in self.commodities)
            + tuple((c.venue, c.symbol) for c in self.controls)
        )

    @property
    def company_count(self) -> int:
        return len(self.companies)

    @property
    def commodity_count(self) -> int:
        return len(self.commodities)

    @property
    def control_count(self) -> int:
        return len(self.controls)

    def by_ticker(self) -> Dict[str, PerpCompany]:
        return {c.ticker: c for c in self.companies}

    def commodities_by_name(self) -> Dict[str, PerpCommodity]:
        return {c.commodity: c for c in self.commodities}

    def controls_by_symbol(self) -> Dict[str, PerpControl]:
        return {c.symbol: c for c in self.controls}


# ---------------------------------------------------------------------------
# Derived tier / flag rules (shared with scripts/perps/measure_closed_liquidity)
# ---------------------------------------------------------------------------

def tier_for_weekend_usd_per_h(value: float) -> str:
    """Return the closed-market liquidity tier for *value* USD per weekend hour."""
    if value < 0:
        raise PerpUniverseError(
            f"weekend_usd_per_h must be >= 0, got {value!r}"
        )
    for tier, floor in TIER_THRESHOLDS:
        if value >= floor:
            return tier
    return "D"


def derive_flags(
    first_bar: date,
    zero_volume_weekend_share: float,
    window_start: date,
) -> Tuple[str, ...]:
    """Return the review flags implied by the measurement."""
    if not 0.0 <= zero_volume_weekend_share <= 1.0:
        raise PerpUniverseError(
            "zero_volume_weekend_share must be in [0, 1], got "
            f"{zero_volume_weekend_share!r}"
        )
    flags: List[str] = []
    if first_bar > window_start:
        flags.append("new")
    if zero_volume_weekend_share > SPARSE_ZERO_VOLUME_SHARE:
        flags.append("sparse")
    return tuple(flags)


# ---------------------------------------------------------------------------
# Primitive validation helpers
# ---------------------------------------------------------------------------

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


def _as_share(value: Any, source: Path | str, key: str) -> float:
    number = _as_number(value, source, key)
    if number > 1.0:
        raise PerpUniverseError(
            f"{_where(source, key)} must be a share in [0, 1], got {value!r}"
        )
    return number


def _as_nonempty_str(value: Any, source: Path | str, key: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PerpUniverseError(
            f"{_where(source, key)} must be a non-empty string, got {value!r}"
        )
    return value.strip()


def _as_date(value: Any, source: Path | str, key: str) -> date:
    text = _as_nonempty_str(value, source, key)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise PerpUniverseError(
            f"{_where(source, key)} must be an ISO date (YYYY-MM-DD), got {text!r}"
        ) from exc


def _as_bool(value: Any, source: Path | str, key: str) -> bool:
    if not isinstance(value, bool):
        raise PerpUniverseError(
            f"{_where(source, key)} must be a boolean, got {value!r}"
        )
    return value


def _require_instrument_type(
    entry: Mapping[str, Any], source: Path | str, key: str
) -> str:
    if "instrument_type" not in entry:
        raise PerpUniverseError(
            f"{_where(source, key + '.instrument_type')} is required: every row is a "
            f"perpetual future (instrument_type: {INSTRUMENT_TYPE})"
        )
    value = _as_nonempty_str(entry["instrument_type"], source, key + ".instrument_type")
    if value != INSTRUMENT_TYPE:
        raise PerpUniverseError(
            f"{_where(source, key + '.instrument_type')} must be "
            f"{INSTRUMENT_TYPE!r} (perps are derivatives, not equities/ETFs/spot); "
            f"got {value!r}"
        )
    return value


def _require_underlying_type(
    entry: Mapping[str, Any],
    source: Path | str,
    key: str,
    allowed: FrozenSet[str],
) -> str:
    value = _as_nonempty_str(entry["underlying_type"], source, key + ".underlying_type")
    if value not in ALLOWED_UNDERLYING_TYPES:
        raise PerpUniverseError(
            f"{_where(source, key + '.underlying_type')} must be one of "
            f"{sorted(ALLOWED_UNDERLYING_TYPES)}, got {value!r}"
        )
    if value not in allowed:
        raise PerpUniverseError(
            f"{_where(source, key + '.underlying_type')} must be one of "
            f"{sorted(allowed)} in this section, got {value!r}"
        )
    return value


def data_source_for_venue(venue: str) -> str:
    """Return the provider code that every row of *venue* must carry."""
    try:
        return VENUE_DATA_SOURCES[venue]
    except KeyError:
        raise PerpUniverseError(
            f"no data_source mapping for venue {venue!r}; known venues: "
            f"{sorted(VENUE_DATA_SOURCES)}"
        ) from None


def _require_data_source(
    entry: Mapping[str, Any], source: Path | str, key: str, venue: str
) -> str:
    """Validate the row's ``data_source`` and its venue pairing."""
    if "data_source" not in entry:
        raise PerpUniverseError(
            f"{_where(source, key + '.data_source')} is required: every perp row "
            f"carries one provider code from {sorted(DATA_SOURCES)}"
        )
    try:
        value = validate_data_source(entry["data_source"])
    except ValueError as exc:
        raise PerpUniverseError(
            f"{_where(source, key + '.data_source')}: {exc}"
        ) from exc
    expected = data_source_for_venue(venue)
    if value != expected:
        raise PerpUniverseError(
            f"{_where(source, key + '.data_source')} must be {expected!r} for venue "
            f"{venue!r}, got {value!r}"
        )
    return value


def _parse_flags(
    raw: Any,
    *,
    source: Path | str,
    key: str,
    expected: Sequence[str],
) -> Tuple[str, ...]:
    if not isinstance(raw, list):
        raise PerpUniverseError(
            f"{_where(source, key)} must be a list, got {type(raw).__name__}"
        )
    flags: List[str] = []
    for position, item in enumerate(raw):
        value = _as_nonempty_str(item, source, f"{key}[{position}]")
        if value not in ALLOWED_FLAGS:
            raise PerpUniverseError(
                f"{_where(source, key + f'[{position}]')} must be one of "
                f"{sorted(ALLOWED_FLAGS)}, got {value!r}"
            )
        if value in flags:
            raise PerpUniverseError(
                f"{_where(source, key)} duplicates flag {value!r}"
            )
        flags.append(value)
    if set(flags) != set(expected):
        raise PerpUniverseError(
            f"{_where(source, key)} is {sorted(flags)}, but the measurement implies "
            f"{sorted(expected)} (new = first bar after window start; sparse = "
            f">{SPARSE_ZERO_VOLUME_SHARE:.0%} zero-volume weekend hours)"
        )
    return tuple(flags)


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


def _parse_liquidity_window(raw: Any, source: Path | str) -> PerpLiquidityWindow:
    entry = _require_mapping(raw, source, "liquidity_window")
    _check_keys(
        entry,
        required=_WINDOW_REQUIRED,
        optional=frozenset(),
        source=source,
        key="liquidity_window",
    )
    start = _as_date(entry["start"], source, "liquidity_window.start")
    end = _as_date(entry["end"], source, "liquidity_window.end")
    if end < start:
        raise PerpUniverseError(
            f"{_where(source, 'liquidity_window')} end {end} precedes start {start}"
        )
    basis = _as_nonempty_str(entry["basis"], source, "liquidity_window.basis")
    return PerpLiquidityWindow(start=start, end=end, basis=basis)


def _parse_instrument_defaults(raw: Any, source: Path | str) -> Mapping[str, Any]:
    entry = _require_mapping(raw, source, "instrument_defaults")
    _check_keys(
        entry,
        required=_DEFAULTS_REQUIRED,
        optional=_DEFAULTS_OPTIONAL,
        source=source,
        key="instrument_defaults",
    )
    _require_instrument_type(entry, source, "instrument_defaults")
    if _as_bool(entry["is_equity"], source, "instrument_defaults.is_equity") is not False:
        raise PerpUniverseError(
            f"{_where(source, 'instrument_defaults.is_equity')} must be false "
            "(perps are derivatives, not equities)"
        )
    if _as_bool(entry["is_derivative"], source, "instrument_defaults.is_derivative") is not True:
        raise PerpUniverseError(
            f"{_where(source, 'instrument_defaults.is_derivative')} must be true"
        )
    contract = _as_nonempty_str(entry["contract"], source, "instrument_defaults.contract")
    if contract != CONTRACT_TYPE:
        raise PerpUniverseError(
            f"{_where(source, 'instrument_defaults.contract')} must be "
            f"{CONTRACT_TYPE!r}, got {contract!r}"
        )
    if "trades_24x7" in entry:
        _as_bool(entry["trades_24x7"], source, "instrument_defaults.trades_24x7")
    return dict(entry)


def _parse_control(raw: Any, source: Path | str, index: int) -> PerpControl:
    key = f"controls[{index}]"
    entry = _require_mapping(raw, source, key)
    _check_keys(
        entry,
        required=_CONTROL_REQUIRED,
        optional=_CONTROL_OPTIONAL,
        source=source,
        key=key,
    )
    instrument_type = _require_instrument_type(entry, source, key)
    underlying_type = _require_underlying_type(
        entry, source, key, CONTROL_UNDERLYING_TYPES
    )
    underlying = _as_nonempty_str(entry["underlying"], source, key + ".underlying")
    venue = _as_nonempty_str(entry["venue"], source, key + ".venue")
    symbol = _as_nonempty_str(entry["symbol"], source, key + ".symbol")
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
    data_source = _require_data_source(entry, source, key, venue)
    quote_currency: Optional[str] = None
    if "quote_currency" in entry:
        quote_currency = _as_nonempty_str(
            entry["quote_currency"], source, key + ".quote_currency"
        )
    return PerpControl(
        venue=venue,
        data_source=data_source,
        symbol=symbol,
        instrument_type=instrument_type,
        underlying_type=underlying_type,
        underlying=underlying,
        quote_currency=quote_currency,
    )


def _parse_company(
    raw: Any,
    source: Path | str,
    index: int,
    window: PerpLiquidityWindow,
) -> PerpCompany:
    key = f"companies[{index}]"
    entry = _require_mapping(raw, source, key)
    _check_keys(
        entry,
        required=_COMPANY_REQUIRED,
        optional=_COMPANY_OPTIONAL,
        source=source,
        key=key,
    )
    instrument_type = _require_instrument_type(entry, source, key)
    underlying_type = _require_underlying_type(
        entry, source, key, COMPANY_UNDERLYING_TYPES
    )
    ticker = _as_nonempty_str(entry["ticker"], source, key + ".ticker")
    if not _TICKER_RE.match(ticker):
        raise PerpUniverseError(
            f"{_where(source, key + '.ticker')} must be an uppercase ticker, got {ticker!r}"
        )
    underlying = _as_nonempty_str(entry["underlying"], source, key + ".underlying")
    if underlying != ticker:
        raise PerpUniverseError(
            f"{_where(source, key + '.underlying')} must match the ticker {ticker!r} "
            f"for a company perpetual, got {underlying!r}"
        )
    venue = _as_nonempty_str(entry["venue"], source, key + ".venue")
    if venue not in ALLOWED_VENUES:
        raise PerpUniverseError(
            f"{_where(source, key + '.venue')} must be one of {sorted(ALLOWED_VENUES)}, "
            f"got {venue!r}"
        )
    if venue != EQUITY_VENUE:
        raise PerpUniverseError(
            f"{_where(source, key + '.venue')} must be {EQUITY_VENUE!r} for company "
            f"perpetuals, got {venue!r}"
        )
    data_source = _require_data_source(entry, source, key, venue)
    dex = _as_nonempty_str(entry["dex"], source, key + ".dex")
    if dex not in ALLOWED_DEXES:
        raise PerpUniverseError(
            f"{_where(source, key + '.dex')} must be one of {sorted(ALLOWED_DEXES)}, "
            f"got {dex!r}"
        )
    symbol = _as_nonempty_str(entry["symbol"], source, key + ".symbol")
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
    tier = _as_nonempty_str(entry["tier"], source, key + ".tier")
    if tier not in ALLOWED_TIERS:
        raise PerpUniverseError(
            f"{_where(source, key + '.tier')} must be one of {sorted(ALLOWED_TIERS)}, "
            f"got {tier!r}"
        )
    weekend = _as_number(
        entry["weekend_usd_per_h"], source, key + ".weekend_usd_per_h"
    )
    closed = _as_number(entry["closed_usd_per_h"], source, key + ".closed_usd_per_h")
    zero_share = _as_share(
        entry["zero_volume_weekend_share"],
        source,
        key + ".zero_volume_weekend_share",
    )
    first_bar = _as_date(entry["first_bar"], source, key + ".first_bar")
    if first_bar > window.end:
        raise PerpUniverseError(
            f"{_where(source, key + '.first_bar')} {first_bar} is after the "
            f"measurement window end {window.end}"
        )
    expected_tier = tier_for_weekend_usd_per_h(weekend)
    if tier != expected_tier:
        raise PerpUniverseError(
            f"{_where(source, key + '.tier')} {tier!r} disagrees with "
            f"weekend_usd_per_h {weekend!r} (expected {expected_tier!r})"
        )
    flags = _parse_flags(
        entry["flags"],
        source=source,
        key=key + ".flags",
        expected=derive_flags(first_bar, zero_share, window.start),
    )
    quote_currency: Optional[str] = None
    if "quote_currency" in entry:
        quote_currency = _as_nonempty_str(
            entry["quote_currency"], source, key + ".quote_currency"
        )
    return PerpCompany(
        ticker=ticker,
        instrument_type=instrument_type,
        underlying_type=underlying_type,
        underlying=underlying,
        venue=venue,
        data_source=data_source,
        dex=dex,
        symbol=symbol,
        tier=tier,
        weekend_usd_per_h=weekend,
        closed_usd_per_h=closed,
        zero_volume_weekend_share=zero_share,
        first_bar=first_bar,
        flags=flags,
        quote_currency=quote_currency,
        alternates=_parse_alternates(
            entry.get("alternates"), source, key + ".alternates", ticker
        ),
    )


def _parse_commodity(
    raw: Any,
    source: Path | str,
    index: int,
    window: PerpLiquidityWindow,
) -> PerpCommodity:
    key = f"commodities[{index}]"
    entry = _require_mapping(raw, source, key)
    _check_keys(
        entry,
        required=_COMMODITY_REQUIRED,
        optional=_COMMODITY_OPTIONAL,
        source=source,
        key=key,
    )
    commodity = _as_nonempty_str(entry["commodity"], source, key + ".commodity")
    if not _COMMODITY_RE.match(commodity):
        raise PerpUniverseError(
            f"{_where(source, key + '.commodity')} must be lowercase snake_case, "
            f"got {commodity!r}"
        )
    instrument_type = _require_instrument_type(entry, source, key)
    underlying_type = _require_underlying_type(
        entry, source, key, COMMODITY_UNDERLYING_TYPES
    )
    venue = _as_nonempty_str(entry["venue"], source, key + ".venue")
    if venue != EQUITY_VENUE:
        raise PerpUniverseError(
            f"{_where(source, key + '.venue')} must be {EQUITY_VENUE!r} for commodity "
            f"perpetuals, got {venue!r}"
        )
    data_source = _require_data_source(entry, source, key, venue)
    dex = _as_nonempty_str(entry["dex"], source, key + ".dex")
    if dex not in ALLOWED_DEXES:
        raise PerpUniverseError(
            f"{_where(source, key + '.dex')} must be one of {sorted(ALLOWED_DEXES)}, "
            f"got {dex!r}"
        )
    symbol = _as_nonempty_str(entry["symbol"], source, key + ".symbol")
    match = _SYMBOL_RE.match(symbol)
    if not match:
        raise PerpUniverseError(
            f"{_where(source, key + '.symbol')} must look like '<dex>:<TICKER>' "
            f"(for example {dex + ':GOLD'!r}), got {symbol!r}"
        )
    if match.group("dex") != dex:
        raise PerpUniverseError(
            f"{_where(source, key + '.symbol')} dex prefix {match.group('dex')!r} "
            f"does not match dex field {dex!r}"
        )
    etfs_raw = entry["etfs"]
    if not isinstance(etfs_raw, list) or not etfs_raw:
        raise PerpUniverseError(
            f"{_where(source, key + '.etfs')} must be a non-empty list of Massive "
            "ETF tickers paired with this commodity perpetual"
        )
    etfs: List[str] = []
    for position, item in enumerate(etfs_raw):
        etf = _as_nonempty_str(item, source, f"{key}.etfs[{position}]")
        if not _ETF_TICKER_RE.match(etf):
            raise PerpUniverseError(
                f"{_where(source, key + f'.etfs[{position}]')} must be an uppercase "
                f"ETF ticker, got {etf!r}"
            )
        if etf in etfs:
            raise PerpUniverseError(
                f"{_where(source, key + '.etfs')} duplicates ETF {etf!r}"
            )
        etfs.append(etf)
    etf_kind = _as_nonempty_str(entry["etf_kind"], source, key + ".etf_kind")
    if etf_kind not in ALLOWED_ETF_KINDS:
        raise PerpUniverseError(
            f"{_where(source, key + '.etf_kind')} must be one of "
            f"{sorted(ALLOWED_ETF_KINDS)}, got {etf_kind!r}"
        )
    tier = _as_nonempty_str(entry["tier"], source, key + ".tier")
    weekend = _as_number(
        entry["weekend_usd_per_h"], source, key + ".weekend_usd_per_h"
    )
    zero_share = _as_share(
        entry["zero_volume_weekend_share"],
        source,
        key + ".zero_volume_weekend_share",
    )
    first_bar = _as_date(entry["first_bar"], source, key + ".first_bar")
    if first_bar > window.end:
        raise PerpUniverseError(
            f"{_where(source, key + '.first_bar')} {first_bar} is after the "
            f"measurement window end {window.end}"
        )
    expected_tier = tier_for_weekend_usd_per_h(weekend)
    if tier != expected_tier:
        raise PerpUniverseError(
            f"{_where(source, key + '.tier')} {tier!r} disagrees with "
            f"weekend_usd_per_h {weekend!r} (expected {expected_tier!r})"
        )
    quote_currency: Optional[str] = None
    if "quote_currency" in entry:
        quote_currency = _as_nonempty_str(
            entry["quote_currency"], source, key + ".quote_currency"
        )
    return PerpCommodity(
        commodity=commodity,
        instrument_type=instrument_type,
        underlying_type=underlying_type,
        venue=venue,
        data_source=data_source,
        dex=dex,
        symbol=symbol,
        etfs=tuple(etfs),
        etf_kind=etf_kind,
        tier=tier,
        weekend_usd_per_h=weekend,
        zero_volume_weekend_share=zero_share,
        first_bar=first_bar,
        flags=derive_flags(first_bar, zero_share, window.start),
        quote_currency=quote_currency,
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
    if version != 4:
        raise PerpUniverseError(
            f"{_where(source, 'version')} must be 4 (the schema this loader "
            f"validates), got {version}"
        )

    instrument_defaults = _parse_instrument_defaults(
        root["instrument_defaults"], source
    )
    liquidity_window = _parse_liquidity_window(root["liquidity_window"], source)

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
        _parse_company(item, source, index, liquidity_window)
        for index, item in enumerate(raw_companies)
    )

    raw_commodities = root.get("commodities", [])
    if not isinstance(raw_commodities, list):
        raise PerpUniverseError(
            f"{_where(source, 'commodities')} must be a list, got "
            f"{type(raw_commodities).__name__}"
        )
    commodities = tuple(
        _parse_commodity(item, source, index, liquidity_window)
        for index, item in enumerate(raw_commodities)
    )

    seen_tickers: Dict[str, int] = {}
    seen_symbols: Dict[str, str] = {}
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
                f"{company.symbol!r} at {seen_symbols[company.symbol]} and index {index}"
            )
        seen_symbols[company.symbol] = f"companies[{index}]"

    seen_commodities: Dict[str, int] = {}
    for index, commodity in enumerate(commodities):
        if commodity.commodity in seen_commodities:
            raise PerpUniverseError(
                f"{_where(source, 'commodities')} has duplicate commodity "
                f"{commodity.commodity!r} at indexes "
                f"{seen_commodities[commodity.commodity]} and {index}"
            )
        seen_commodities[commodity.commodity] = index
        if commodity.symbol in seen_symbols:
            raise PerpUniverseError(
                f"{_where(source, 'commodities')} provider symbol "
                f"{commodity.symbol!r} duplicates {seen_symbols[commodity.symbol]}"
            )
        seen_symbols[commodity.symbol] = f"commodities[{index}]"

    overlap = set(seen_tickers) & set(control_symbols)
    if overlap:
        raise PerpUniverseError(
            f"{_where(source, 'document')} uses ticker(s) both as company and control: "
            f"{sorted(overlap)}"
        )

    return PerpUniverse(
        version=version,
        instrument_defaults=instrument_defaults,
        liquidity_window=liquidity_window,
        controls=controls,
        companies=companies,
        commodities=commodities,
        selected_at=selected_at,
        selection=selection,
        path=Path(source),
    )


class _UniqueKeySafeLoader(yaml.SafeLoader):
    """``SafeLoader`` that rejects duplicate mapping keys.

    ``yaml.safe_load`` keeps only the last occurrence of a duplicate key without
    raising, and every row of ``config/perp_universe.yaml`` is a single-line flow
    mapping: a copy-paste error with two ``symbol:`` or two ``tier:`` keys in one
    row would load silently with the later value. ``_check_keys`` cannot see it
    because it inspects the already-merged dict, so the duplicate is rejected at
    parse time here instead.
    """

    def construct_mapping(self, node, deep=False):
        if isinstance(node, yaml.MappingNode):
            seen = set()
            for key_node, _ in node.value:
                key = self.construct_object(key_node, deep=deep)
                try:
                    duplicate = key in seen
                except TypeError as exc:  # pragma: no cover - unhashable key
                    raise yaml.constructor.ConstructorError(
                        None, None, f"unhashable mapping key {key!r}", key_node.start_mark
                    ) from exc
                if duplicate:
                    raise yaml.constructor.ConstructorError(
                        None, None, f"duplicate mapping key {key!r}", key_node.start_mark
                    )
                seen.add(key)
        return super().construct_mapping(node, deep=deep)


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
        document = yaml.load(text, Loader=_UniqueKeySafeLoader)  # noqa: S506 - SafeLoader subclass
    except yaml.YAMLError as exc:
        raise PerpUniverseError(f"{resolved}: invalid YAML: {exc}") from exc
    return _parse_document(document, resolved)


if __name__ == "__main__":
    universe = load_perp_universe()
    print(
        f"perp universe v{universe.version}: {universe.company_count} companies, "
        f"{universe.commodity_count} commodities, {universe.control_count} controls "
        f"({universe.path})"
    )
    print("controls:", ", ".join(f"{c.venue}:{c.symbol}" for c in universe.controls))
    print("tickers:", ", ".join(universe.tickers))
    print("commodities:", ", ".join(universe.commodity_symbols))
