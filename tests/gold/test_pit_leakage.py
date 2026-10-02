"""tests/gold/test_pit_leakage.py — future-invariance (no-look-ahead) test.

Point-in-time correctness is proven by *future-invariance*, the standard
look-ahead check, run against the **real** gold OHLCV feature SQL (extracted
verbatim from ``gold/01_gold_ohlcv_features.sql``) on a local DataFrame
(DuckDB). The old ``pit_guard`` comparator test is gone: it proved only that an
in-memory timestamp helper raises, and the build never called it, so it could
not detect the intraday ``session_high`` leak.

Future-invariance definition:
    For a cut time ``t``, compute the gold features from the silver input
    truncated at ``t``, and again from the full input. Every feature row with
    ``feature_ts <= t`` must be **identical** in both runs. A look-ahead window
    (e.g. the old whole-day ``MAX(high) OVER (PARTITION BY symbol, DATE(...))``)
    breaks this, because an early bar's ``session_high`` then changes when the
    afternoon bars are added.

The DuckDB execution is a faithful adaptation of the production SELECT: the
window expressions are copied byte-for-byte from the build file; only the
Databricks-specific table FQN, the ``universe``/date-range filters and
``current_timestamp()`` are substituted for a local table / ``now()``.
``processed_ts`` (a wall-clock metadata column) is excluded from the comparison.

Run standalone (the project ``conftest.py`` imports ``db.database``, which does
not exist on this branch):

    python3 -m pytest tests/gold/test_pit_leakage.py --noconftest -v
"""
from __future__ import annotations

import os
from datetime import datetime

import duckdb
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SQL_PATH = os.path.join(REPO, "gold", "01_gold_ohlcv_features.sql")

CUT = datetime(2026, 1, 5, 10, 30, 0)  # bar-2 close of day 1

_SYMBOLS = ["AAA", "BBB"]
_DAYS = ["2026-01-05", "2026-01-06"]
_BAR_TIMES = ["09:30:00", "10:30:00", "11:30:00", "12:30:00"]


def _extract_feature_sql(path: str = SQL_PATH, old_session_high: bool = False) -> str:
    """Return the production feature SELECT (WITH ... FROM feats) from the build.

    The window expressions are copied verbatim; only the parts that cannot run
    against a local DataFrame (the Delta table FQN, the ``universe`` temp view
    filter, the ``{date_start}``/``{date_end}`` placeholders and
    ``current_timestamp()``) are adapted for DuckDB.
    """
    text = open(path, encoding="utf-8").read()
    start = text.index("WITH lagged AS")
    end = text.index("FROM feats") + len("FROM feats")
    sql = text[start:end]
    sql = sql.replace("bootcamp_students.evangoh_capstone.silver_ohlcv", "silver_ohlcv")
    sql = sql.replace("AND symbol IN (SELECT symbol FROM universe)", "")
    sql = sql.replace("AND DATE(event_ts) >= '{date_start}' AND DATE(event_ts) < '{date_end}'", "")
    sql = sql.replace("current_timestamp()", "now()")
    if old_session_high:
        sql = sql.replace(
            "MAX(high) OVER (PARTITION BY symbol, DATE(event_ts) ORDER BY event_ts "
            "ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS session_high",
            "MAX(high) OVER (PARTITION BY symbol, DATE(event_ts)) AS session_high",
        )
        sql = sql.replace(
            "MIN(low)  OVER (PARTITION BY symbol, DATE(event_ts) ORDER BY event_ts "
            "ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS session_low",
            "MIN(low)  OVER (PARTITION BY symbol, DATE(event_ts)) AS session_low",
        )
    return sql


def _silver_rows() -> list[tuple]:
    """2 symbols x 2 days x 4 bars. high rises and low falls across the day so a
    whole-day MAX/MIN differs from the trailing value at an early bar."""
    rows = []
    for sym in _SYMBOLS:
        for day in _DAYS:
            for i, t in enumerate(_BAR_TIMES, start=1):
                high = 10.0 * i
                low = 10.0 * i - 1.0
                close = high
                rows.append((sym, f"{day} {t}", close, high, low, 1000.0, close, "minute"))
    return rows


def _run(sql: str, rows: list[tuple], cutoff: datetime | None) -> dict[tuple, dict]:
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE silver_ohlcv("
        "symbol VARCHAR, event_ts TIMESTAMP, close DOUBLE, high DOUBLE, "
        "low DOUBLE, volume DOUBLE, vwap DOUBLE, timespan VARCHAR)"
    )
    con.executemany("INSERT INTO silver_ohlcv VALUES (?,?,?,?,?,?,?,?)", rows)
    if cutoff is not None:
        con.execute("DELETE FROM silver_ohlcv WHERE event_ts > ?", [cutoff])
    result = con.execute(sql).fetchall()
    cols = [d[0] for d in con.description]
    con.close()
    return {(r[0], r[1]): dict(zip(cols, r)) for r in result}


def _mismatches(
    full: dict[tuple, dict], trunc: dict[tuple, dict], cutoff: datetime
) -> list[tuple]:
    out = []
    for key, d in full.items():
        if d["feature_ts"] > cutoff:
            continue
        t = trunc.get(key)
        if t is None:
            out.append((key, "missing-in-truncated-run", None, None))
            continue
        for c, v in d.items():
            if c == "processed_ts":
                continue
            if v != t[c]:
                out.append((key, c, t[c], v))
    return out


def test_production_sql_uses_trailing_session_window():
    """Guard: the build must actually carry the trailing (not whole-day) frame."""
    text = open(SQL_PATH, encoding="utf-8").read()
    trailing = (
        "MAX(high) OVER (PARTITION BY symbol, DATE(event_ts) ORDER BY event_ts "
        "ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)"
    )
    assert trailing in text
    assert "MAX(high) OVER (PARTITION BY symbol, DATE(event_ts)) AS session_high" not in text


def test_future_invariance_holds_for_fixed_sql():
    sql = _extract_feature_sql(old_session_high=False)
    full = _run(sql, _silver_rows(), cutoff=None)
    trunc = _run(sql, _silver_rows(), cutoff=CUT)
    mismatches = _mismatches(full, trunc, CUT)
    assert mismatches == [], f"look-ahead detected: {mismatches[:5]}"


def test_old_session_high_window_is_detected_as_leak():
    """Negative control: the pre-fix whole-day window must fail invariance.

    This codifies that the test can actually catch the historical look-ahead —
    a future-invariance test that cannot fail on the old SQL is worthless.
    """
    sql = _extract_feature_sql(old_session_high=True)
    full = _run(sql, _silver_rows(), cutoff=None)
    trunc = _run(sql, _silver_rows(), cutoff=CUT)
    mismatches = _mismatches(full, trunc, CUT)
    assert mismatches, "old session-high window did NOT break future-invariance"
    assert any(m[1] == "dist_session_high" for m in mismatches)
