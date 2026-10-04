"""Pure, dependency-free helpers shared by the streaming DLT pipeline and its tests.

Nothing in this module imports ``pyspark`` or ``dlt``/``pyspark.pipelines`` so the
correctness-critical logic (dedup key, availability timestamp, quarantine reasons)
can be unit tested on a laptop without Spark. Pipeline files import these functions
directly and wrap them in Spark UDFs where a column expression is needed.

The pipeline reads the production ``bronze_ohlcv`` table as a stream. Its schema is:

    symbol, event_ts, open, high, low, close, volume (bigint), vwap,
    trade_count (int), timespan, source, raw_payload, ingest_ts

Design rules enforced here (these mirror the batch silver/gold layer, which had four
point-in-time leaks that must not be repeated):

* Minute bars are stamped at bar **start** (Polygon convention), so a bar's
  ``information_available_ts = event_ts + bar interval``.
* The business key ``(symbol, event_ts, timespan)`` collapses re-delivered source rows.
* Malformed rows are quarantined with a stable, machine-readable reason.
"""

from __future__ import annotations

import hashlib
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

UTC = timezone.utc

# Field separator unlikely to appear in source values (deterministic event ids).
_SEP = "\x1f"

# Business key that identifies one logical bar. Streaming Silver dedup uses this
# exact tuple so re-delivered source rows collapse deterministically.
BUSINESS_KEY_FIELDS: tuple[str, ...] = ("symbol", "event_ts", "timespan")

# Seconds covered by a supported bar timespan. ``event_ts`` marks the bar *start*,
# so ``event_ts + interval_seconds(timespan)`` is the bar close.
_INTERVAL_SECONDS: dict[str, int] = {
    "minute": 60,
    "hour": 3_600,
    "day": 86_400,
}

# Production tables this pipeline must never own or write. A declared ``dlt_`` table
# name that equals any of these is a blocking defect.
REAL_TABLE_NAMES: frozenset[str] = frozenset(
    {
        "bronze_ohlcv",
        "silver_ohlcv",
        "silver_ohlcv_quarantine",
        "silver_ohlcv_quarantine_batch",
        "gold_ohlcv_features",
    }
)


def normalize_symbol(symbol: Any) -> str | None:
    """Trim and upper-case a symbol so case variants key together."""

    if symbol is None:
        return None
    cleaned = str(symbol).strip().upper()
    return cleaned or None


def normalize_timespan(timespan: Any) -> str | None:
    """Trim and lower-case a bar timespan so case variants key together."""

    if timespan is None:
        return None
    cleaned = str(timespan).strip().lower()
    return cleaned or None


def _parse_iso(text: str) -> datetime:
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("empty timestamp string")
    if cleaned.endswith(("Z", "z")):
        cleaned = cleaned[:-1] + "+00:00"
    return datetime.fromisoformat(cleaned)


def to_utc(value: datetime | str) -> datetime:
    """Return a timezone-aware UTC datetime.

    Naive datetimes and strings without an offset are interpreted as UTC, which
    matches how Spark stores timestamps. Aware values are converted.
    """

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = _parse_iso(value)
    else:
        raise TypeError(f"unsupported timestamp type: {type(value).__name__}")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def format_utc(value: datetime | str) -> str:
    """Canonical ISO-8601 UTC string, e.g. ``2024-01-02T00:05:00+00:00``."""

    return to_utc(value).isoformat()


def interval_seconds(timespan: str) -> int:
    """Seconds covered by a supported bar timespan."""

    key = str(timespan).strip().lower()
    if key not in _INTERVAL_SECONDS:
        raise ValueError(f"unsupported timespan: {timespan!r}")
    return _INTERVAL_SECONDS[key]


def bar_close_ts(event_ts: datetime | str, timespan: str) -> datetime:
    """UTC instant when a bar covering ``timespan`` from ``event_ts`` closes."""

    return to_utc(event_ts) + timedelta(seconds=interval_seconds(timespan))


def derive_information_available_ts(event_ts: datetime | str, timespan: str) -> datetime:
    """Point-in-time availability timestamp for a bar.

    A bar is not knowable before it closes, so ``information_available_ts`` is the
    bar close: ``event_ts + interval_seconds(timespan)``. This mirrors the batch
    gold convention (minute bars: ``event_ts + INTERVAL 1 MINUTE``) and prevents
    look-ahead in downstream feature joins.
    """

    return bar_close_ts(event_ts, timespan)


def business_key(symbol: Any, event_ts: Any, timespan: Any) -> tuple[str, str, str]:
    """Normalised, deterministic ``(symbol, event_ts, timespan)`` business key."""

    sym = normalize_symbol(symbol)
    span = normalize_timespan(timespan)
    if sym is None or span is None:
        raise ValueError("symbol and timespan must be non-empty")
    return (sym, format_utc(to_utc(event_ts)), span)


def dedup_hash(symbol: Any, event_ts: Any, timespan: Any) -> str:
    """Deterministic SHA-256 dedup key for the stable business key."""

    payload = _SEP.join(business_key(symbol, event_ts, timespan)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def safe_dedup_hash(symbol: Any, event_ts: Any, timespan: Any) -> str | None:
    """Exception-safe :func:`dedup_hash` for streaming UDFs."""

    try:
        return dedup_hash(symbol, event_ts, timespan)
    except (TypeError, ValueError):
        return None


def safe_derive_information_available_ts(
    event_ts: Any, timespan: Any
) -> datetime | None:
    """Exception-safe :func:`derive_information_available_ts` for streaming UDFs."""

    try:
        return derive_information_available_ts(event_ts, timespan)
    except (TypeError, ValueError):
        return None


def latency_seconds(later_ts: Any, earlier_ts: Any) -> float:
    """Wall-clock seconds between two UTC instants (``later - earlier``).

    Turns the stamped pipeline timestamps (``ingest_ts``, ``*_processed_ts``) into
    latency numbers. A negative result means the two timestamps are out of order.
    """

    return (to_utc(later_ts) - to_utc(earlier_ts)).total_seconds()


def window_completion_ingest_ts(ingest_ts_values: Iterable[Any]) -> datetime:
    """The ``ingest_ts`` that completes a window's output: the *latest* contributing bar.

    End-to-end latency must be measured from the bar that completes the output, not the
    earliest one. Measuring from the earliest would count the whole window length as
    pipeline latency and make even an instant pipeline appear to miss the <60s SLO.
    """

    values = [to_utc(v) for v in ingest_ts_values]
    if not values:
        raise ValueError("cannot determine completion ingest_ts of an empty window")
    return max(values)


def _as_number(value: Any) -> float | None:
    """Coerce a source value to a finite float, or ``None`` if not a valid number."""

    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value)
        except ValueError:
            return None
    else:
        return None
    return number if math.isfinite(number) else None


def validate_bar(record: Mapping[str, Any]) -> list[str]:
    """Return a sorted list of quarantine reasons for a raw OHLCV bar.

    An empty list means the bar is valid. Reasons are stable, machine-readable
    tokens so the quarantine table stays queryable.
    """

    reasons: set[str] = set()

    symbol = record.get("symbol")
    if symbol is None or not str(symbol).strip():
        reasons.add("missing_symbol")

    try:
        to_utc(record.get("event_ts"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        reasons.add("invalid_event_ts")

    timespan = record.get("timespan")
    if timespan is None or not str(timespan).strip():
        reasons.add("missing_timespan")
    else:
        try:
            interval_seconds(str(timespan))
        except ValueError:
            reasons.add("unsupported_timespan")

    numbers: dict[str, float | None] = {
        field: _as_number(record.get(field))
        for field in ("open", "high", "low", "close", "volume", "vwap", "trade_count")
    }
    for field in ("open", "high", "low", "close"):
        if numbers[field] is None:
            reasons.add(f"invalid_{field}")

    open_, high, low, close = (
        numbers["open"],
        numbers["high"],
        numbers["low"],
        numbers["close"],
    )
    if None not in (open_, high, low, close):
        assert open_ is not None and high is not None and low is not None and close is not None
        if high < low:
            reasons.add("high_below_low")
        if high < max(open_, close, low):
            reasons.add("high_below_components")
        if low > min(open_, close, high):
            reasons.add("low_above_components")
        if min(open_, high, low, close) < 0:
            reasons.add("negative_price")

    if numbers["volume"] is not None and numbers["volume"] < 0:
        reasons.add("negative_volume")

    if numbers["trade_count"] is not None and numbers["trade_count"] < 0:
        reasons.add("negative_trade_count")

    vwap = numbers["vwap"]
    if vwap is not None and high is not None and low is not None and (vwap < low or vwap > high):
        reasons.add("vwap_out_of_range")

    return sorted(reasons)


def is_valid_bar(record: Mapping[str, Any]) -> bool:
    """Convenience predicate for :func:`validate_bar`."""

    return not validate_bar(record)
