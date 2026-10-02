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


# ---------------------------------------------------------------------------
# Round 5: daily options availability (start-of-day stamp leak)
#
# bronze_options_day is stamped at the START of the day (event_ts = 04:00/05:00
# UTC = midnight New York) but its volume covers the WHOLE session. Round 4's
# future-invariance test covered OHLCV only, so it could not see this. These
# tests pin (1) that the build SQL no longer derives availability from the
# start-of-day stamp, (2) that the availability invariant flags the old stamp,
# and (3) that the gold_model_features AS-OF join excludes same-day options for
# an intraday prediction.
# ---------------------------------------------------------------------------

OPTIONS_SQL_PATH = os.path.join(REPO, "gold", "02_gold_options_features.sql")
QUOTES_SQL_PATH = os.path.join(REPO, "silver", "03_silver_options_quotes.sql")

# Summer date (America/New_York is EDT, UTC-4): session close 16:00 ET = 20:00 UTC,
# so the fixed availability (close + 30m buffer) is 20:30 UTC.
SESSION_CLOSE_SUMMER = "2026-07-07 20:00:00"
INFO_TS_SUMMER = "2026-07-07 20:30:00"
# The old start-of-day stamp (midnight New York in EDT) for the same feature day.
START_OF_DAY_SUMMER = "2026-07-07 04:00:00"


def test_options_availability_not_derived_from_event_ts():
    """Guard: the options build must not timestamp availability with the daily
    bar's own (start-of-day) event_ts. The old `MAX(event_ts)` / `last_ts`
    expression is the leak this round fixes."""
    text = open(OPTIONS_SQL_PATH, encoding="utf-8").read()
    assert "information_available_ts" in text
    assert "last_ts AS information_available_ts" not in text
    assert "MAX(event_ts)" not in text
    assert "convert_timezone('America/New_York', 'UTC'" in text
    assert "make_interval(0, 0, 0, 0, 0, opt_pub_buffer_minutes, 0)" in text


def test_options_sql_has_named_buffer_constant():
    """Guard: the publication buffer must be a named constant, not a magic 30."""
    text = open(OPTIONS_SQL_PATH, encoding="utf-8").read()
    assert "DECLARE OR REPLACE VARIABLE opt_pub_buffer_minutes INT DEFAULT 30" in text
    assert "opt_pub_buffer_minutes" in text


def test_silver_quotes_is_stale_uses_snapshot_time():
    """Guard: is_stale compares against the single snapshot time, not the
    per-underlying whole-day MAX (which flags earlier quotes as stale)."""
    text = open(QUOTES_SQL_PATH, encoding="utf-8").read()
    assert "MAX(participant_ts) OVER ()" in text
    assert "MAX(participant_ts) OVER (PARTITION BY underlying)" not in text


def _run_availability_invariant(info_ts_rows: list[tuple]) -> int:
    """Portable reproduction of the build's availability invariant (options):
    COUNT rows where information_available_ts < session close of the feature
    date. Returns the number of violating rows."""
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE opt(symbol VARCHAR, feature_ts TIMESTAMP, "
        "information_available_ts TIMESTAMP, session_close TIMESTAMP)"
    )
    con.executemany("INSERT INTO opt VALUES (?,?,?,?)", info_ts_rows)
    n = con.execute(
        "SELECT COUNT(*) FROM opt WHERE information_available_ts < session_close"
    ).fetchone()[0]
    con.close()
    return n


def test_options_availability_invariant_catches_start_of_day_stamp():
    """The availability invariant must flag the old 04:00 start-of-day stamp and
    pass the fixed session-close + buffer stamp."""
    fixed = [("AAA", "2026-07-07 00:00:00", INFO_TS_SUMMER, SESSION_CLOSE_SUMMER)]
    broken = [("AAA", "2026-07-07 00:00:00", START_OF_DAY_SUMMER, SESSION_CLOSE_SUMMER)]
    assert _run_availability_invariant(fixed) == 0, "fixed info_ts must satisfy invariant"
    assert _run_availability_invariant(broken) == 1, "start-of-day stamp must violate invariant"


def _run_asof_join(options_rows: list[tuple], predictions: list[tuple]) -> dict:
    """Portable reproduction of gold_model_features.opt_join: AS-OF join on
    information_available_ts <= prediction_ts, keep the latest available."""
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE opt(symbol VARCHAR, feature_ts TIMESTAMP, "
        "information_available_ts TIMESTAMP, put_call_ratio DOUBLE)"
    )
    con.executemany("INSERT INTO opt VALUES (?,?,?,?)", options_rows)
    con.execute("CREATE TABLE spine(symbol VARCHAR, prediction_ts TIMESTAMP)")
    con.executemany("INSERT INTO spine VALUES (?,?)", predictions)
    rows = con.execute(
        """
        SELECT symbol, prediction_ts, put_call_ratio
        FROM (
          SELECT db.symbol, db.prediction_ts, opt.put_call_ratio,
                 ROW_NUMBER() OVER (PARTITION BY db.symbol, db.prediction_ts
                                    ORDER BY opt.information_available_ts DESC) AS rn
          FROM spine db
          JOIN opt ON opt.symbol = db.symbol
                  AND opt.information_available_ts <= db.prediction_ts
        ) WHERE rn = 1
        """
    ).fetchall()
    con.close()
    return {str(r[1]): r[2] for r in rows}


def test_model_features_asof_join_excludes_same_day_options_intraday():
    """Future-invariance for gold_model_features: an intraday prediction (15:00
    UTC, before the 16:00 ET close) must see the PRIOR day's options, not the
    same day's. The old start-of-day stamp would leak the same-day volume."""
    options_fixed = [
        ("AAA", "2026-07-06 00:00:00", "2026-07-06 20:30:00", 1.5),  # day d-1
        ("AAA", "2026-07-07 00:00:00", INFO_TS_SUMMER, 2.0),          # day d (fixed)
    ]
    options_broken = [
        ("AAA", "2026-07-06 00:00:00", "2026-07-06 20:30:00", 1.5),
        ("AAA", "2026-07-07 00:00:00", START_OF_DAY_SUMMER, 2.0),     # day d (old bug)
    ]
    pred = [("AAA", "2026-07-07 15:00:00")]

    fixed = _run_asof_join(options_fixed, pred)
    assert fixed[pred[0][1]] == 1.5, f"intraday prediction leaked same-day options: {fixed}"

    broken = _run_asof_join(options_broken, pred)
    assert broken[pred[0][1]] == 2.0, (
        "negative control failed: start-of-day stamp did not leak same-day options"
    )


# ---------------------------------------------------------------------------
# Round 6: minute-bar availability (start-of-bar stamp leak)
#
# gold_ohlcv_features stamped information_available_ts = event_ts, but minute
# bars are labelled at their START (Polygon: event_ts marks [t, t+1min)); a
# bar's close is known only at t+1min. These tests pin (1) that the build SQL
# derives availability from timespan (event_ts + INTERVAL 1 MINUTE for minute
# bars, not the raw event_ts) and (2) that the availability invariant flags the
# old stamp and passes the fixed one.
# ---------------------------------------------------------------------------

OHLCV_SQL_PATH = os.path.join(REPO, "gold", "01_gold_ohlcv_features.sql")


def test_ohlcv_availability_derived_from_timespan():
    """Guard: the OHLCV build must not timestamp availability with the raw bar
    event_ts. The old `event_ts AS information_available_ts` is the leak."""
    text = open(OHLCV_SQL_PATH, encoding="utf-8").read()
    assert "event_ts                                   AS information_available_ts" not in text
    assert "CASE timespan" in text
    assert "event_ts + INTERVAL 1 MINUTE" in text


def _run_minute_invariant(info_ts_rows: list[tuple]) -> int:
    """Portable reproduction of the build's minute availability invariant:
    COUNT rows where information_available_ts < feature_ts + INTERVAL 1 MINUTE."""
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE ohlcv(symbol VARCHAR, feature_ts TIMESTAMP, "
        "information_available_ts TIMESTAMP)"
    )
    con.executemany("INSERT INTO ohlcv VALUES (?,?,?)", info_ts_rows)
    n = con.execute(
        "SELECT COUNT(*) FROM ohlcv "
        "WHERE information_available_ts < feature_ts + INTERVAL 1 MINUTE"
    ).fetchone()[0]
    con.close()
    return n


def test_minute_availability_invariant_catches_start_of_bar_stamp():
    """The invariant must flag the old event_ts stamp and pass event_ts + 1 min."""
    fixed = [("AAA", "2026-07-07 15:59:00", "2026-07-07 16:00:00")]
    broken = [("AAA", "2026-07-07 15:59:00", "2026-07-07 15:59:00")]
    assert _run_minute_invariant(fixed) == 0, "fixed info_ts must satisfy invariant"
    assert _run_minute_invariant(broken) == 1, "start-of-bar stamp must violate invariant"
