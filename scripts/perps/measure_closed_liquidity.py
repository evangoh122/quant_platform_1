#!/usr/bin/env python3
"""Measure closed-market (weekend) liquidity for the perp universe.

This is the productised version of the round-1 one-off measurement script.  It
answers one question for every instrument in ``config/perp_universe.yaml``:

    How much notional trades per hour while the NYSE is **closed**?

Method
------
* Candles are 1h provider candles (notional = ``volume * close``).
* A session is a regular NYSE session from ``config/market_calendar.py``: the
  static holiday file supplies full closures and recurring 13:00 early closes.
* A bar counts as **closed-market** only when the whole half-open interval
  ``[bar_start, bar_end)`` lies outside every session.  A bar that straddles an
  open or close boundary (e.g. the Monday 09:00-10:00 ET bar when the session
  opens at 09:30 ET) is neither fully closed nor a session bar and is excluded
  from ``closed_usd_per_h``; bars are partitioned into ``closed_bars`` and
  ``open_bars`` (any overlap with a session).
* ``weekend_usd_per_h`` divides the weekend notional by the **expected** hours
  of the covered weekend breaks, not by the number of bars returned: a missing
  hour is a real zero-notional hour and must not raise the mean.  The same
  denominator drives ``zero_volume_weekend_share`` and ``weekend_gap_hours``
  (``expected - observed``), and ``weekend_coverage`` is the observed share.
* Weekend breaks come from :func:`config.market_calendar.weekend_window`, so a
  Monday holiday ends the window on Tuesday 09:30 ET and a Friday holiday
  (e.g. Good Friday) starts it on Thursday 16:00 ET.  Only breaks that contain
  at least one bar are used for the expected-hours denominator (an instrument
  listed mid-window is measured over the weekends it existed for and carries
  the ``new`` flag).
* Tiers (``A >= 250k``, ``B >= 50k``, ``C >= 10k``, ``D < 10k``) and flags
  (``new`` = first bar after the window start, ``sparse`` = more than 25% of
  expected weekend hours with zero volume) come from the loader's shared rules.
  A tier is **withheld** (``proposed_tier: null`` plus ``tier_withheld_reason``)
  when the observed weekend coverage is below
  :data:`MIN_WEEKEND_COVERAGE` (80%) of the expected hours: a mean computed
  from a handful of bars is not a measurement.
* Every proposal row carries ``data_source`` — the provider code from
  ``config/data_sources.py`` (validated; ``hyperliquid`` for this measurement) —
  so a tier proposal is traceable to the source that measured it.
* Every proposal row also carries ``instrument_type`` from
  ``config.perp_universe.INSTRUMENT_TYPE`` (``perpetual_future``): the measured
  instrument is a derivative, never the equity/ETF it tracks.

Safety
------
``--dry-run`` is the default and makes **zero network calls**.  ``--live`` is
required to fetch candles.  ``--candles-dir`` reads recorded candle fixtures
(offline, used by the tests).  The tool only ever writes a *proposal* JSON; it
never edits ``config/perp_universe.yaml`` — the owner applies tier changes.

Usage::

    python scripts/perps/measure_closed_liquidity.py                # plan only
    python scripts/perps/measure_closed_liquidity.py --live \
        --out docs/data/perp_liquidity_tier_proposal.json
    python scripts/perps/measure_closed_liquidity.py \
        --candles-dir /tmp/perp-candles --out /tmp/proposal.json
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time as time_module
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from datetime import time as wall_time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib import error as urlerror
from urllib import request as urlrequest
from zoneinfo import ZoneInfo

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from config.data_sources import validate_data_source  # noqa: E402
from config.market_calendar import (  # noqa: E402
    early_close_dates,
    is_trading_day,
    weekend_window,
)
from config.perp_universe import (  # noqa: E402
    INSTRUMENT_TYPE,
    SPARSE_ZERO_VOLUME_SHARE,
    TIER_THRESHOLDS,
    PerpUniverse,
    derive_flags,
    load_perp_universe,
    tier_for_weekend_usd_per_h,
)

NY = ZoneInfo("America/New_York")
UTC = timezone.utc

HYPERLIQUID_INFO_URL = "https://api.hyperliquid.xyz/info"
DEFAULT_OUT = _REPO_ROOT / "docs" / "data" / "perp_liquidity_tier_proposal.json"
DEFAULT_RATE_LIMIT_RPS = 2.0
DEFAULT_RETRIES = 4
DEFAULT_TIMEOUT = 30.0
MAX_RATE_LIMIT_RPS = 2.0
#: Public ``candleSnapshot`` page cap used for forward paging.
MAX_CANDLES_PER_REQUEST = 5000
#: Minimum observed share of the expected weekend hours before a tier is
#: proposed.  Below this the mean is a handful of bars, not a measurement.
MIN_WEEKEND_COVERAGE = 0.80


class MeasureError(RuntimeError):
    """Raised for malformed candle payloads or exhausted network retries."""


@dataclass(frozen=True)
class Candle:
    start_ts: datetime
    end_ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    trades: int

    def __post_init__(self) -> None:
        # Boundary arithmetic ("is this bar inside the closed window?") is only
        # defined for timezone-aware instants.  A naive datetime would silently
        # be compared in an arbitrary zone, so it is rejected rather than
        # guessed (the market calendar rejects naive input for the same reason).
        for field in ("start_ts", "end_ts"):
            value = getattr(self, field)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(
                    f"Candle.{field} must be timezone-aware (UTC), got {value!r}"
                )
        if self.end_ts <= self.start_ts:
            raise ValueError(
                f"Candle.end_ts must be after start_ts, got "
                f"{self.start_ts!r}..{self.end_ts!r}"
            )

    @property
    def notional(self) -> float:
        return self.volume * self.close

    @property
    def hours(self) -> float:
        return (self.end_ts - self.start_ts).total_seconds() / 3600.0


# ---------------------------------------------------------------------------
# Pure helpers (exercised directly by the tests)
# ---------------------------------------------------------------------------

def _as_int(value: Any, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise MeasureError(f"{field} must be an integer, got {value!r}") from exc


def _as_float(value: Any, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise MeasureError(f"{field} must be numeric, got {value!r}") from exc


def parse_candle_payload(payload: Any) -> List[Candle]:
    """Normalise a Hyperliquid ``candleSnapshot`` page."""
    if not isinstance(payload, list):
        raise MeasureError("candleSnapshot payload must be a list")
    candles: List[Candle] = []
    for index, raw in enumerate(payload):
        if not isinstance(raw, Mapping):
            raise MeasureError(f"candle[{index}] must be an object")
        for key in ("t", "T", "o", "h", "l", "c", "v"):
            if key not in raw:
                raise MeasureError(f"candle[{index}] missing {key!r}")
        start_ms = _as_int(raw["t"], f"candle[{index}].t")
        end_ms = _as_int(raw["T"], f"candle[{index}].T")
        if end_ms <= start_ms:
            raise MeasureError(
                f"candle[{index}].T must be after .t, got {start_ms}..{end_ms}"
            )
        candles.append(
            Candle(
                start_ts=datetime.fromtimestamp(start_ms / 1000.0, tz=UTC),
                end_ts=datetime.fromtimestamp(end_ms / 1000.0, tz=UTC),
                open=_as_float(raw["o"], f"candle[{index}].o"),
                high=_as_float(raw["h"], f"candle[{index}].h"),
                low=_as_float(raw["l"], f"candle[{index}].l"),
                close=_as_float(raw["c"], f"candle[{index}].c"),
                volume=_as_float(raw["v"], f"candle[{index}].v"),
                trades=_as_int(raw.get("n", 0), f"candle[{index}].n"),
            )
        )
    candles.sort(key=lambda candle: candle.start_ts)
    return candles


def is_regular_session(moment: datetime, path: str | Path | None = None) -> bool:
    """Return True when *moment* falls inside a regular NYSE session."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(f"moment must be timezone-aware, got {moment!r}")
    local = moment.astimezone(NY)
    day = local.date()
    if not is_trading_day(day, path):
        return False
    close = wall_time(13, 0) if day in early_close_dates(path) else wall_time(16, 0)
    return wall_time(9, 30) <= local.time().replace(tzinfo=None) < close


def bar_overlaps_session(candle: Candle, path: str | Path | None = None) -> bool:
    """True when any part of ``[start, end)`` lies inside a regular session."""
    return is_regular_session(candle.start_ts, path) or is_regular_session(
        candle.end_ts - timedelta(microseconds=1), path
    )


def bar_is_fully_closed(candle: Candle, path: str | Path | None = None) -> bool:
    """True only when the whole bar lies outside every session.

    A bar that straddles a session boundary (for example Monday 09:00-10:00 ET
    when the session opens at 09:30 ET) is *not* a closed-market bar: half of
    its volume belongs to the session.
    """
    return not bar_overlaps_session(candle, path)


def weekend_windows_for(
    start: date,
    end: date,
    path: str | Path | None = None,
) -> List[Tuple[datetime, datetime]]:
    """Return every weekend break fully inside ``[start, end]`` (UTC)."""
    if end < start:
        raise MeasureError(f"end {end} precedes start {start}")
    start_utc = datetime.combine(start, wall_time(0, 0), tzinfo=UTC)
    end_utc = datetime.combine(end + timedelta(days=1), wall_time(0, 0), tzinfo=UTC)
    day = start
    while day.weekday() != 4:
        day += timedelta(days=1)
    windows: List[Tuple[datetime, datetime]] = []
    while day <= end:
        # ``weekend_window`` returns (last session close, next session open), so
        # the first value opens the *break* and the second closes it.
        window_start_utc, window_end_utc = weekend_window(day, path=path)
        if window_start_utc >= start_utc and window_end_utc <= end_utc:
            windows.append((window_start_utc, window_end_utc))
        day += timedelta(days=7)
    return windows


def in_weekend(candle: Candle, windows: Sequence[Tuple[datetime, datetime]]) -> bool:
    """A bar belongs to the weekend only when the whole bar is inside it."""
    return any(
        start <= candle.start_ts and candle.end_ts <= end for start, end in windows
    )


def _mean(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


def _window_hours(window: Tuple[datetime, datetime]) -> float:
    start, end = window
    return (end - start).total_seconds() / 3600.0


def measure_candles(
    candles: Iterable[Candle],
    windows: Sequence[Tuple[datetime, datetime]],
    *,
    path: str | Path | None = None,
) -> Dict[str, Any]:
    """Compute closed-market liquidity metrics for one instrument.

    Both ``weekend_usd_per_h`` and ``zero_volume_weekend_share`` use the
    **expected** hours of the covered weekend breaks as the denominator, so an
    hour with no bar counts as a zero-notional hour instead of disappearing
    from the mean.
    """
    empty: Dict[str, Any] = {
        "bars": 0,
        "first_bar": None,
        "weekend_bars": 0,
        "weekend_usd_per_h": None,
        "closed_usd_per_h": None,
        "open_usd_per_h": None,
        "closed_bars": 0,
        "open_bars": 0,
        "covered_weekends": 0,
        "expected_hours": None,
        "observed_hours": None,
        "weekend_gap_hours": None,
        "weekend_coverage": None,
        "zero_volume_weekend_share": None,
    }
    ordered = sorted(candles, key=lambda candle: candle.start_ts)
    if not ordered:
        return empty
    weekend = [candle for candle in ordered if in_weekend(candle, windows)]
    covered_windows = [
        window
        for window in windows
        if any(in_weekend(candle, (window,)) for candle in weekend)
    ]
    expected_hours = sum(_window_hours(window) for window in covered_windows)
    observed_hours = sum(candle.hours for candle in weekend)
    zero_hours = sum(candle.hours for candle in weekend if candle.volume == 0)
    coverage = observed_hours / expected_hours if expected_hours > 0 else None
    closed = [candle.notional for candle in ordered if bar_is_fully_closed(candle, path)]
    opened = [
        candle.notional for candle in ordered if bar_overlaps_session(candle, path)
    ]
    weekend_notional = sum(candle.notional for candle in weekend)
    return {
        "bars": len(ordered),
        "first_bar": ordered[0].start_ts.date().isoformat(),
        "weekend_bars": len(weekend),
        "weekend_usd_per_h": (
            weekend_notional / expected_hours if expected_hours > 0 else None
        ),
        "closed_usd_per_h": _mean(closed),
        "open_usd_per_h": _mean(opened),
        "closed_bars": len(closed),
        "open_bars": len(opened),
        "covered_weekends": len(covered_windows),
        "expected_hours": expected_hours if expected_hours > 0 else None,
        "observed_hours": observed_hours,
        "weekend_gap_hours": (
            expected_hours - observed_hours if expected_hours > 0 else None
        ),
        "weekend_coverage": coverage,
        "zero_volume_weekend_share": (
            zero_hours / expected_hours if expected_hours > 0 else None
        ),
    }


def _round(value: Optional[float], places: int = 2) -> Optional[float]:
    return None if value is None else round(value, places)


def _proposal_row(
    *,
    identifier: str,
    symbol: str,
    instrument_type: str = INSTRUMENT_TYPE,
    underlying_type: str,
    data_source: str,
    current_tier: str,
    current_flags: Sequence[str],
    measurement: Mapping[str, Any],
    window_start: date,
) -> Dict[str, Any]:
    if instrument_type != INSTRUMENT_TYPE:
        raise MeasureError(
            f"{identifier}: instrument_type must be {INSTRUMENT_TYPE!r} "
            f"(perps are derivatives, not equities/ETFs), got "
            f"{instrument_type!r}"
        )
    try:
        data_source = validate_data_source(data_source)
    except ValueError as exc:
        raise MeasureError(f"{identifier}: {exc}") from exc
    weekend = measurement.get("weekend_usd_per_h")
    coverage = measurement.get("weekend_coverage")
    proposed_tier: Optional[str] = None
    withheld_reason: Optional[str] = None
    if weekend is None:
        withheld_reason = "no weekend bars in the measured breaks"
    elif coverage is not None and float(coverage) < MIN_WEEKEND_COVERAGE:
        withheld_reason = (
            f"weekend bar coverage {float(coverage):.1%} of the expected hours is "
            f"below the {MIN_WEEKEND_COVERAGE:.0%} minimum"
        )
    else:
        proposed_tier = tier_for_weekend_usd_per_h(float(weekend))
    first_bar = measurement.get("first_bar")
    zero_share = measurement.get("zero_volume_weekend_share")
    proposed_flags: Optional[List[str]] = None
    if first_bar is not None and zero_share is not None:
        proposed_flags = list(
            derive_flags(
                date.fromisoformat(first_bar),
                float(zero_share),
                window_start,
            )
        )
    return {
        "id": identifier,
        "symbol": symbol,
        "instrument_type": instrument_type,
        "underlying_type": underlying_type,
        "data_source": data_source,
        "current_tier": current_tier,
        "proposed_tier": proposed_tier,
        "tier_withheld_reason": withheld_reason,
        "tier_changed": proposed_tier is not None and proposed_tier != current_tier,
        "current_flags": list(current_flags),
        "proposed_flags": proposed_flags,
        "flags_changed": proposed_flags is not None
        and sorted(proposed_flags) != sorted(current_flags),
        "weekend_usd_per_h": _round(weekend),
        "closed_usd_per_h": _round(measurement.get("closed_usd_per_h")),
        "zero_volume_weekend_share": _round(zero_share, 4),
        "weekend_coverage": _round(coverage, 4),
        "expected_hours": _round(measurement.get("expected_hours"), 2),
        "weekend_gap_hours": _round(measurement.get("weekend_gap_hours"), 2),
        "first_bar": first_bar,
        "bars": measurement.get("bars", 0),
    }


def build_proposal(
    universe: PerpUniverse,
    measurements: Mapping[str, Mapping[str, Any]],
    *,
    window_start: date,
    window_end: date,
    generated_at: datetime,
    mode: str,
) -> Dict[str, Any]:
    """Build the proposed tier update.  The config file is never modified."""
    companies = []
    for company in universe.companies:
        measurement = measurements.get(company.symbol) or measurements.get(
            company.ticker
        ) or {}
        companies.append(
            _proposal_row(
                identifier=company.ticker,
                symbol=company.symbol,
                instrument_type=company.instrument_type,
                underlying_type=company.underlying_type,
                data_source=company.data_source,
                current_tier=company.tier,
                current_flags=company.flags,
                measurement=measurement,
                window_start=window_start,
            )
        )
    commodities = []
    for commodity in universe.commodities:
        measurement = measurements.get(commodity.symbol) or measurements.get(
            commodity.commodity
        ) or {}
        row = _proposal_row(
            identifier=commodity.commodity,
            symbol=commodity.symbol,
            instrument_type=commodity.instrument_type,
            underlying_type=commodity.underlying_type,
            data_source=commodity.data_source,
            current_tier=commodity.tier,
            current_flags=commodity.flags,
            measurement=measurement,
            window_start=window_start,
        )
        row["etfs"] = list(commodity.etfs)
        row["etf_kind"] = commodity.etf_kind
        commodities.append(row)
    return {
        "version": 1,
        "note": (
            "Proposal only. config/perp_universe.yaml is not modified; the owner "
            "applies tier/flag changes."
        ),
        "generated_at": generated_at.isoformat(),
        "mode": mode,
        "window": {
            "start": window_start.isoformat(),
            "end": window_end.isoformat(),
            "basis": "weekend_closed_market_hours",
        },
        "thresholds": {
            "A": TIER_THRESHOLDS[0][1],
            "B": TIER_THRESHOLDS[1][1],
            "C": TIER_THRESHOLDS[2][1],
            "D": "< C",
            "sparse_zero_volume_share_above": SPARSE_ZERO_VOLUME_SHARE,
            "min_weekend_coverage": MIN_WEEKEND_COVERAGE,
            "denominator": "expected_hours_of_covered_weekend_breaks",
        },
        "companies": companies,
        "commodities": commodities,
    }


def render_summary(proposal: Mapping[str, Any]) -> str:
    """Human-readable summary of the proposal (stdout only)."""
    rows = list(proposal.get("companies", [])) + list(proposal.get("commodities", []))
    changed = [row for row in rows if row.get("tier_changed")]
    no_data = [row for row in rows if row.get("proposed_tier") is None]
    withheld = [
        row
        for row in no_data
        if row.get("weekend_coverage") is not None
    ]
    lines = [
        f"window: {proposal['window']['start']} -> {proposal['window']['end']}",
        f"instruments measured: {len(rows) - len(no_data)} of {len(rows)}",
        f"tier changes proposed: {len(changed)}",
        f"tiers withheld for low weekend coverage: {len(withheld)}",
    ]
    for row in changed:
        lines.append(
            f"  {row['id']}: {row['current_tier']} -> {row['proposed_tier']} "
            f"({row['weekend_usd_per_h']} USD/h)"
        )
    for row in withheld:
        lines.append(f"  {row['id']}: withheld — {row['tier_withheld_reason']}")
    if no_data:
        lines.append("no weekend bars: " + ", ".join(row["id"] for row in no_data))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Offline fixtures
# ---------------------------------------------------------------------------

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def fixture_path(directory: Path, *candidates: str) -> Optional[Path]:
    """Return the first existing fixture file for the given names."""
    for candidate in candidates:
        path = directory / f"{_SAFE_NAME_RE.sub('_', candidate)}.json"
        if path.is_file():
            return path
    return None


def load_fixture_candles(directory: Path, *candidates: str) -> List[Candle]:
    path = fixture_path(directory, *candidates)
    if path is None:
        raise MeasureError(
            f"no candle fixture for {candidates[0]!r} in {directory}"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MeasureError(f"cannot read candle fixture {path}: {exc}") from exc
    return parse_candle_payload(payload)


# ---------------------------------------------------------------------------
# Live client
# ---------------------------------------------------------------------------

class RateLimiter:
    """Minimum-interval limiter (default and maximum 2 requests/second)."""

    def __init__(self, max_rps: float = DEFAULT_RATE_LIMIT_RPS) -> None:
        if max_rps <= 0:
            raise MeasureError("--rate-limit must be > 0")
        if max_rps > MAX_RATE_LIMIT_RPS:
            raise MeasureError(
                f"--rate-limit must be <= {MAX_RATE_LIMIT_RPS} requests/second "
                "(polite-use cap)"
            )
        self.min_interval = 1.0 / max_rps
        self._last = 0.0

    def wait(self) -> None:
        now = time_module.monotonic()
        delay = self.min_interval - (now - self._last)
        if delay > 0:
            time_module.sleep(delay)
        self._last = time_module.monotonic()


class HttpClient:
    """Minimal stdlib HTTP client with rate limiting and retry/backoff.

    Retries use exponential backoff **plus jitter**: a fleet of polite clients
    that all retry on the same 429/5xx boundary would otherwise synchronise and
    retry in lockstep.  ``rng`` is injectable so tests can pin the jitter.
    """

    def __init__(
        self,
        *,
        max_rps: float = DEFAULT_RATE_LIMIT_RPS,
        retries: int = DEFAULT_RETRIES,
        backoff_seconds: float = 1.0,
        jitter_fraction: float = 0.5,
        timeout: float = DEFAULT_TIMEOUT,
        limiter: Optional[RateLimiter] = None,
        rng: Optional[random.Random] = None,
        urlopen: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.retries = max(0, retries)
        self.backoff_seconds = max(0.0, backoff_seconds)
        self.jitter_fraction = min(max(0.0, jitter_fraction), 1.0)
        self.timeout = timeout
        self.limiter = limiter or RateLimiter(max_rps)
        self._rng = rng or random.Random()
        self._urlopen = urlopen or urlrequest.urlopen

    def post_json(self, url: str, body: Mapping[str, Any]) -> Any:
        raw = self._request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MeasureError(f"{url}: invalid JSON response: {exc}") from exc

    def _request(
        self,
        url: str,
        *,
        data: Optional[bytes] = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> str:
        request_headers = {
            "User-Agent": "quant-platform-perps-liquidity/1.0",
            **(headers or {}),
        }
        last_error: Optional[BaseException] = None
        for attempt in range(self.retries + 1):
            self.limiter.wait()
            request = urlrequest.Request(
                url,
                data=data,
                headers=dict(request_headers),
                method="POST" if data is not None else "GET",
            )
            try:
                with self._urlopen(request, timeout=self.timeout) as response:
                    return response.read().decode("utf-8")
            except urlerror.HTTPError as exc:
                last_error = exc
                retryable = exc.code == 429 or 500 <= exc.code < 600
                if not retryable or attempt >= self.retries:
                    raise MeasureError(
                        f"{url}: HTTP {exc.code} {exc.reason}"
                    ) from exc
                delay = self._delay(attempt)
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                if retry_after:
                    try:
                        delay = max(delay, float(retry_after))
                    except ValueError:
                        pass
                time_module.sleep(delay)
            except (urlerror.URLError, TimeoutError, ConnectionError, OSError) as exc:
                last_error = exc
                if attempt >= self.retries:
                    raise MeasureError(f"{url}: {type(exc).__name__}: {exc}") from exc
                time_module.sleep(self._delay(attempt))
        raise MeasureError(f"{url}: exhausted retries ({last_error})")

    def _delay(self, attempt: int) -> float:
        """Exponential backoff with upward-only jitter (never shortens a wait)."""
        base = self.backoff_seconds * (2 ** attempt)
        return base * (1.0 + self._rng.random() * self.jitter_fraction)


def fetch_candles(
    client: Any,
    symbol: str,
    *,
    start: date,
    end: date,
) -> List[Candle]:
    """Fetch 1h candles for ``[start, end]``, paging by startTime."""
    start_ms = int(datetime.combine(start, wall_time(0, 0), tzinfo=UTC).timestamp() * 1000)
    end_ms = int(
        datetime.combine(end + timedelta(days=1), wall_time(0, 0), tzinfo=UTC).timestamp()
        * 1000
    )
    cursor = start_ms
    by_start: Dict[int, Candle] = {}
    while cursor < end_ms:
        body = {
            "type": "candleSnapshot",
            "req": {
                "coin": symbol,
                "interval": "1h",
                "startTime": cursor,
                "endTime": end_ms,
            },
        }
        page = parse_candle_payload(client.post_json(HYPERLIQUID_INFO_URL, body))
        if not page:
            break
        for candle in page:
            by_start[int(candle.start_ts.timestamp() * 1000)] = candle
        if len(page) < MAX_CANDLES_PER_REQUEST:
            break
        cursor = int(page[-1].start_ts.timestamp() * 1000) + 1
    return [by_start[key] for key in sorted(by_start)]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_plan(universe: PerpUniverse, out: Path) -> None:
    instruments = [
        *(company.symbol for company in universe.companies),
        *(commodity.symbol for commodity in universe.commodities),
    ]
    print("mode: dry-run (no network; pass --live or --candles-dir)")
    print(
        f"instruments: {universe.company_count} companies + "
        f"{universe.commodity_count} commodities (controls are not measured)"
    )
    print(f"planned requests: {len(instruments)} candleSnapshot 1h streams")
    for symbol in instruments[:10]:
        print(f"  POST {HYPERLIQUID_INFO_URL} {symbol} 1h")
    if len(instruments) > 10:
        print(f"  ... {len(instruments) - 10} more")
    print(f"proposal WOULD be written to {out} with --live/--candles-dir")
    print("config/perp_universe.yaml is never modified by this tool")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--live",
        action="store_true",
        help="fetch candles from the Hyperliquid info API (default is a plan)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the plan and make no network calls (default)",
    )
    parser.add_argument(
        "--candles-dir",
        default=None,
        help="directory of recorded 1h candle fixtures (offline measurement)",
    )
    parser.add_argument("--perps", default=None, help="perp universe YAML")
    parser.add_argument(
        "--symbols",
        default=None,
        help="comma-separated tickers/symbols to measure (default: all)",
    )
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument(
        "--start",
        default=None,
        help="measurement window start date (default: universe liquidity_window.start)",
    )
    parser.add_argument(
        "--end",
        default=None,
        help="measurement window end date (default: universe liquidity_window.end)",
    )
    parser.add_argument("--rate-limit", type=float, default=DEFAULT_RATE_LIMIT_RPS)
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    args = parser.parse_args(argv)

    if args.live and args.dry_run:
        parser.error("--live and --dry-run are mutually exclusive")
    if args.live and args.candles_dir:
        parser.error("--live and --candles-dir are mutually exclusive")

    universe = load_perp_universe(args.perps)
    window_start = (
        date.fromisoformat(args.start) if args.start else universe.liquidity_window.start
    )
    window_end = (
        date.fromisoformat(args.end) if args.end else universe.liquidity_window.end
    )
    try:
        windows = weekend_windows_for(window_start, window_end)
    except MeasureError as exc:
        parser.error(str(exc))
    out = Path(args.out)

    if not args.live and not args.candles_dir:
        _print_plan(universe, out)
        return 0

    measurements: Dict[str, Dict[str, Any]] = {}
    selected = (
        {item.strip() for item in args.symbols.split(",") if item.strip()}
        if args.symbols
        else None
    )
    try:
        if args.candles_dir:
            directory = Path(args.candles_dir)
            for company in universe.companies:
                if selected is not None and not (
                    {company.ticker, company.symbol} & selected
                ):
                    continue
                candles = load_fixture_candles(
                    directory, company.ticker, company.symbol
                )
                measurements[company.symbol] = measure_candles(candles, windows)
            for commodity in universe.commodities:
                if selected is not None and not (
                    {commodity.commodity, commodity.symbol} & selected
                ):
                    continue
                candles = load_fixture_candles(
                    directory, commodity.commodity, commodity.symbol
                )
                measurements[commodity.symbol] = measure_candles(candles, windows)
            mode = "fixtures"
        else:
            client = HttpClient(
                max_rps=args.rate_limit,
                retries=args.retries,
                timeout=args.timeout,
            )
            for company in universe.companies:
                if selected is not None and not (
                    {company.ticker, company.symbol} & selected
                ):
                    continue
                candles = fetch_candles(
                    client, company.symbol, start=window_start, end=window_end
                )
                measurements[company.symbol] = measure_candles(candles, windows)
            for commodity in universe.commodities:
                if selected is not None and not (
                    {commodity.commodity, commodity.symbol} & selected
                ):
                    continue
                candles = fetch_candles(
                    client, commodity.symbol, start=window_start, end=window_end
                )
                measurements[commodity.symbol] = measure_candles(candles, windows)
            mode = "live"
    except MeasureError as exc:
        print(f"measurement failed: {exc}", file=sys.stderr)
        return 2

    proposal = build_proposal(
        universe,
        measurements,
        window_start=window_start,
        window_end=window_end,
        generated_at=datetime.now(timezone.utc),
        mode=mode,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(proposal, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    print(render_summary(proposal))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
