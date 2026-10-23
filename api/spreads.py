"""api/spreads.py — Polars computations for the Market Spreads screen.

Pure functions over rows read through the existing retrieval contracts
(``agent.tools_retrieval``).  Every number the screen shows is computed here —
the frontend only draws what the API returns.

Data-correctness rules enforced here:

* two-leg series are **inner joined** on the date.  A date present in only one
  leg is dropped and counted (``dropped_dates``); it is never forward-filled.
* relative performance is **rebased to 100 at the first common date of the
  window**.  The ``adj_*`` columns of ``silver_ohlcv_day_adjusted`` are
  global/current-scale split-adjusted levels, approved for returns but not as
  price levels, so the ratio is only meaningful as a rebased index.
* ``bronze_fed_series`` stores multiple vintages per
  ``(series_id, observation_date)``.  Only the latest ``vintage_date``
  (tie-break ``ingest_ts``) survives, otherwise the yield chart double-counts a
  day.  Null values are dropped.
* fewer than two points is ``empty`` — never zeros, never an error.

Computation is Polars only; there is no dataframe-library fallback here.
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from typing import Any

import polars as pl

#: Base level of a rebased relative-performance index.
INDEX_BASE = 100.0

#: Exact label required for rebased relative-performance series.
INDEX_LABEL = (
    "relative performance, rebased to 100, price return "
    "(splits adjusted, dividends not)"
)


def _as_date(value: Any) -> date | None:
    """Coerce a date/datetime/ISO string to a ``datetime.date`` (or None)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _as_float(value: Any) -> float | None:
    """Coerce a numeric/string value to a finite float.

    FRED writes missing observations as ``"."`` in the source CSV; those land in
    the lakehouse as null, but a literal ``"."`` (or a blank) is treated the same
    way here so a malformed row is dropped rather than crashing the cast.
    """
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text or text == ".":
            return None
        try:
            value = float(text)
        except ValueError:
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _positive_base(value: Any) -> float | None:
    """Return ``value`` as a finite, strictly positive float, else ``None``.

    A price level at or below zero cannot anchor a rebased index: dividing by it
    either raises (zero denominator) or gives a sign-flipped index (negative
    level).  Callers treat ``None`` as "no usable base" and return the empty
    result instead of raising.
    """
    number = _as_float(value)
    if number is None or number <= 0:
        return None
    return number


def _first_date(frame: pl.DataFrame) -> date | None:
    """First ``event_date`` of a non-empty frame, defensively coerced."""
    if frame.height == 0 or "event_date" not in frame.columns:
        return None
    return _as_date(frame["event_date"][0])


def _sort_key(value: Any) -> str:
    """Return a lexicographically sortable ISO text key for a date/timestamp."""
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _window(frame: pl.DataFrame, window_start: date | None) -> pl.DataFrame:
    """Keep rows on/after ``window_start`` (defensive: the read is already bounded)."""
    if window_start is None or frame.height == 0:
        return frame
    return frame.filter(pl.col("event_date") >= pl.lit(window_start, dtype=pl.Date))


def _value_frame(
    rows: Iterable[dict],
    *,
    date_key: str = "event_date",
    value_key: str = "close",
) -> pl.DataFrame:
    """Build a ``(event_date, value)`` frame, dropping rows with a missing leg."""
    records: list[dict[str, Any]] = []
    for row in rows or ():
        event_date = _as_date(row.get(date_key))
        value = _as_float(row.get(value_key))
        if event_date is None or value is None:
            continue
        records.append({"event_date": event_date, "value": value})
    if not records:
        return pl.DataFrame(schema={"event_date": pl.Date, "value": pl.Float64})
    return pl.DataFrame(records).with_columns(
        pl.col("event_date").cast(pl.Date),
        pl.col("value").cast(pl.Float64),
    )


def _fed_frame(rows: Iterable[dict]) -> pl.DataFrame:
    """Build the de-vintaged FRED frame: one row per (series_id, observation_date).

    Keeps the latest ``vintage_date`` per observation, tie-broken by
    ``ingest_ts``.  Null and ``"."`` values are dropped before deduplication.
    """
    records: list[dict[str, Any]] = []
    for row in rows or ():
        series_id = str(row.get("series_id") or "").strip().upper()
        observation_date = _as_date(row.get("observation_date"))
        value = _as_float(row.get("value"))
        if not series_id or observation_date is None or value is None:
            continue
        records.append(
            {
                "series_id": series_id,
                "event_date": observation_date,
                "value": value,
                "vintage_key": _sort_key(row.get("vintage_date")),
                "ingest_key": _sort_key(row.get("ingest_ts")),
            }
        )
    if not records:
        return pl.DataFrame(
            schema={
                "series_id": pl.Utf8,
                "event_date": pl.Date,
                "value": pl.Float64,
                "vintage_key": pl.Utf8,
                "ingest_key": pl.Utf8,
            }
        )
    return (
        pl.DataFrame(records)
        .with_columns(
            pl.col("event_date").cast(pl.Date),
            pl.col("value").cast(pl.Float64),
        )
        .sort(["vintage_key", "ingest_key"])
        .unique(subset=["series_id", "event_date"], keep="last")
    )


def _orphan_count(left: pl.DataFrame, right: pl.DataFrame) -> int:
    """Count dates that exist in only one of the two legs (no forward-fill)."""
    only_left = (
        left.select("event_date")
        .join(right.select("event_date"), on="event_date", how="anti")
        .height
    )
    only_right = (
        right.select("event_date")
        .join(left.select("event_date"), on="event_date", how="anti")
        .height
    )
    return only_left + only_right


def _empty_result(**extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "points": [],
        "first_common_date": None,
        "dropped_dates": 0,
        "empty": True,
        "latest_value": None,
        "latest_date": None,
        "window_pct_change": None,
        "as_of": None,
    }
    result.update(extra)
    return result


def price_series(
    rows: Sequence[dict],
    *,
    window_start: date | None = None,
) -> dict[str, Any]:
    """Single-leg split-adjusted price series (e.g. USO ``adj_close``).

    Returns ``points`` as ``[[ISO date, value], ...]`` plus the latest value and
    window percentage change.  Fewer than two points is ``empty``.
    """
    frame = _window(_value_frame(rows), window_start).sort("event_date")
    if frame.height < 2:
        result = _empty_result()
        result["dropped_dates"] = 0
        return result

    dates = frame["event_date"].to_list()
    values = [round(float(v), 6) for v in frame["value"].to_list()]
    points = [[d.isoformat(), v] for d, v in zip(dates, values)]
    first_value = values[0]
    pct_change = None
    if _positive_base(first_value) is not None:
        pct_change = round((values[-1] / first_value - 1.0) * 100.0, 4)
    return {
        "points": points,
        "first_common_date": dates[0].isoformat(),
        "dropped_dates": 0,
        "empty": False,
        "latest_value": values[-1],
        "latest_date": dates[-1].isoformat(),
        "window_pct_change": pct_change,
        "as_of": dates[-1].isoformat(),
    }


def rebased_relative_index(
    rows_a: Sequence[dict],
    rows_b: Sequence[dict],
    *,
    symbol_a: str = "A",
    symbol_b: str = "B",
    window_start: date | None = None,
) -> dict[str, Any]:
    """Rebased relative-performance index of leg A over leg B.

    ``ratio = adj_close_a / adj_close_b`` on dates present in **both** legs,
    then ``index = ratio / ratio(first common date) * 100``.  The result is a
    price-return index (splits adjusted, dividends not) — never the raw ratio
    presented as a price.
    """
    left = _window(_value_frame(rows_a), window_start).rename({"value": "value_a"})
    right = _window(_value_frame(rows_b), window_start).rename({"value": "value_b"})
    dropped = _orphan_count(left, right)
    result = _empty_result(symbol_a=symbol_a, symbol_b=symbol_b)
    result["dropped_dates"] = dropped

    common = left.join(right, on="event_date", how="inner").sort("event_date")
    first_common = _first_date(common)
    if first_common is None:
        return result

    result["first_common_date"] = first_common.isoformat()
    if common.height < 2:
        return result

    # Validate BOTH legs before dividing.  Dividing by the unguarded denominator
    # raised ZeroDivisionError for a zero close and 500'd the whole route.
    base_a = _positive_base(common["value_a"][0])
    base_b = _positive_base(common["value_b"][0])
    if base_a is None or base_b is None:
        return result
    base_ratio = base_a / base_b
    if not math.isfinite(base_ratio):
        return result

    indexed = common.with_columns(
        ((pl.col("value_a") / pl.col("value_b")) / base_ratio * INDEX_BASE).alias("index")
    ).filter(pl.col("index").is_finite())
    if indexed.height < 2:
        return result

    dates = indexed["event_date"].to_list()
    values = [round(float(v), 6) for v in indexed["index"].to_list()]
    result.update(
        {
            "points": [[d.isoformat(), v] for d, v in zip(dates, values)],
            "empty": False,
            "latest_value": values[-1],
            "latest_date": dates[-1].isoformat(),
            "window_pct_change": round((values[-1] / INDEX_BASE - 1.0) * 100.0, 4),
            "as_of": dates[-1].isoformat(),
        }
    )
    return result


def yield_curve(
    rows: Sequence[dict],
    *,
    window_start: date | None = None,
    long_series: str = "DGS10",
    short_series: str = "DGS2",
) -> dict[str, Any]:
    """10Y/2Y Treasury yields on common observation dates, plus the 10s2s spread.

    ``rows`` are raw ``bronze_fed_series`` rows (any revision_class); only the
    two requested series are used, after collapsing to the latest vintage per
    observation.  The spread is ``long_series - short_series`` on dates present
    in both legs, matching FRED's own ``T10Y2Y`` definition.
    """
    frame = _window(_fed_frame(rows), window_start)
    ten = frame.filter(pl.col("series_id") == long_series).select(
        "event_date", pl.col("value").alias("value_10")
    )
    two = frame.filter(pl.col("series_id") == short_series).select(
        "event_date", pl.col("value").alias("value_2")
    )
    dropped = _orphan_count(ten, two)
    result: dict[str, Any] = _empty_result(
        long_series=long_series,
        short_series=short_series,
        points={long_series: [], short_series: []},
        spread_points=[],
        spread_value=None,
        spread_as_of=None,
    )
    result["dropped_dates"] = dropped

    common = ten.join(two, on="event_date", how="inner").sort("event_date")
    first_common = _first_date(common)
    if first_common is None:
        return result

    result["first_common_date"] = first_common.isoformat()
    if common.height < 2:
        return result

    dates = common["event_date"].to_list()
    tens = [round(float(v), 6) for v in common["value_10"].to_list()]
    twos = [round(float(v), 6) for v in common["value_2"].to_list()]
    if not all(math.isfinite(v) for v in (*tens, *twos)):
        return result
    spreads = [[d.isoformat(), round(t - w, 6)] for d, t, w in zip(dates, tens, twos)]
    if not all(math.isfinite(point[1]) for point in spreads):
        return result

    result.update(
        {
            "points": {
                long_series: [[d.isoformat(), v] for d, v in zip(dates, tens)],
                short_series: [[d.isoformat(), v] for d, v in zip(dates, twos)],
            },
            "spread_points": spreads,
            "spread_value": spreads[-1][1],
            "spread_as_of": dates[-1].isoformat(),
            "empty": False,
            "latest_value": tens[-1],
            "latest_date": dates[-1].isoformat(),
            "window_pct_change": None,
            "as_of": dates[-1].isoformat(),
        }
    )
    return result
