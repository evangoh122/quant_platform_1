"""tests/gold/test_gold_log_returns.py — log-return features on gold_ohlcv_features.

``gold/01_gold_ohlcv_features.sql`` now emits ``log_return_1m/5m/15m/30m`` beside
``return_*``: ``LN(close / NULLIF(LAG(close, N) OVER (PARTITION BY symbol,
DATE(event_ts) ORDER BY event_ts), 0))`` guarded by ``CASE WHEN ratio > 0`` so a
missing lag bar or a non-positive ratio yields NULL (never NaN / -Infinity).

Three layers of proof, all offline (no Spark, no network):

1. SQL text structure: LN( + the ratio > 0 guard + the exact same
   (symbol, session-day) LAG windows as return_N, and no cross-day lag.
2. Behaviour: the real CTE chain extracted verbatim from the build file runs in
   DuckDB against a synthetic multi-symbol/two-session series (zero close,
   negative close, one-bar gap) and must match a pure-Python reference
   implementation of the window math, including ``log_return_N == ln(1 +
   return_N)`` wherever defined and NULL on day boundaries / bad ratios.
3. Contracts: db/schema_contract.py requires the four columns and the final
   SELECT projects exactly the contract column set; the pipeline column-diff
   helper ``ensure_gold_ohlcv_log_return_columns`` adds only missing columns,
   is idempotent, and runs before the gold_ohlcv_features step.

Mutation proofs (see .agents/evidence/gold-log-returns-r1.md):
(a) drop the ``crN > 0`` guard       -> NULL/identity tests fail
(b) change a LAG offset / partition  -> identity / day-boundary tests fail
(c) drop a column from the SELECT    -> contract test fails
(d) run against a main archive       -> these tests fail
"""
from __future__ import annotations

import math
import os
import re
from datetime import datetime, timedelta

import duckdb
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SQL_PATH = os.path.join(REPO, "gold", "01_gold_ohlcv_features.sql")
PIPELINE_PATH = os.path.join(REPO, "pipelines", "run_silver_gold.py")
METRICS_PATH = os.path.join(REPO, "ontology", "metric_definitions.yaml")

HORIZONS = (1, 5, 15, 30)
LOG_RETURN_COLUMNS = [f"log_return_{n}m" for n in HORIZONS]
RETURN_COLUMNS = [f"return_{n}m" for n in HORIZONS]

DAY1 = "2026-01-05"
DAY2 = "2026-01-06"
BARS_PER_SESSION = 35  # > 30 bars so log_return_30m is in-session reachable


# ---------------------------------------------------------------------------
# SQL extraction (DuckDB shim, same adaptation as tests/gold/test_pit_leakage.py)
# ---------------------------------------------------------------------------

def _extract_feature_sql() -> str:
    """Return the production feature SELECT (WITH ... FROM feats) from the build.

    Window expressions are copied verbatim; only the Delta table FQN, the
    ``universe`` filter, the ``{date_start}``/``{date_end}`` placeholders and
    ``current_timestamp()`` are adapted for DuckDB.
    """
    text = open(SQL_PATH, encoding="utf-8").read()
    start = text.index("WITH lagged AS")
    end = text.index("FROM feats") + len("FROM feats")
    sql = text[start:end]
    sql = sql.replace("bootcamp_students.evangoh_capstone.silver_ohlcv", "silver_ohlcv")
    sql = sql.replace("AND symbol IN (SELECT symbol FROM universe)", "")
    sql = sql.replace(
        "AND DATE(event_ts) >= '{date_start}' AND DATE(event_ts) < '{date_end}'", ""
    )
    sql = sql.replace("current_timestamp()", "now()")
    return sql


def _final_select_columns() -> list[str]:
    """Column names projected by the MERGE source's final SELECT (before FROM feats)."""
    text = open(SQL_PATH, encoding="utf-8").read()
    end = text.index("FROM feats")
    start = text.rindex("SELECT", 0, end)
    select_list = text[start + len("SELECT"):end]
    cols: list[str] = []
    for part in _split_top_level_commas(select_list):
        part = re.sub(r"--.*", "", part).strip()
        if not part:
            continue
        alias = re.search(r"\bAS\s+(\w+)\s*$", part, re.I)
        if alias:
            cols.append(alias.group(1))
        else:
            bare = re.fullmatch(r"(\w+)", part)
            assert bare, f"unparsed projection {part!r}"
            cols.append(bare.group(1))
    return cols


def _split_top_level_commas(value: str) -> list[str]:
    parts, start, depth = [], 0, 0
    for index, char in enumerate(value):
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            parts.append(value[start:index])
            start = index + 1
    parts.append(value[start:])
    return parts


# ---------------------------------------------------------------------------
# Pure-Python reference of the window math
# ---------------------------------------------------------------------------

def _reference(rows: list[tuple[str, datetime, float]]) -> dict[tuple, dict]:
    """Reference implementation of the gold return/log-return window math.

    ``rows`` are (symbol, event_ts, close) silver bars. For each (symbol,
    DATE(event_ts)) partition ordered by event_ts, ``return_N`` is
    ``close / NULLIF(LAG(close, N), 0) - 1`` and ``log_return_N`` is
    ``LN(ratio)`` guarded by ``ratio > 0`` — NULL when the lag bar is missing
    (row offset N absent inside the session) or the ratio is non-positive.
    """
    partitions: dict[tuple[str, str], list[tuple[datetime, float]]] = {}
    for sym, ts, close in rows:
        partitions.setdefault((sym, ts.date().isoformat()), []).append((ts, close))

    out: dict[tuple, dict] = {}
    for (_sym, _day), part in partitions.items():
        part = sorted(part, key=lambda x: x[0])
        for i, (ts, close) in enumerate(part):
            rec: dict = {}
            for n in HORIZONS:
                j = i - n
                ratio = None
                if j >= 0 and part[j][1] != 0:
                    ratio = close / part[j][1]
                rec[f"return_{n}m"] = None if ratio is None else ratio - 1.0
                rec[f"log_return_{n}m"] = (
                    math.log(ratio) if ratio is not None and ratio > 0 else None
                )
            out[(_sym, ts)] = rec
    return out


# ---------------------------------------------------------------------------
# Synthetic series: several symbols, two sessions, zero close, negative close,
# and a one-bar gap (LAG counts rows, so offsets must cross the gap correctly).
# ---------------------------------------------------------------------------

def _synthetic_rows() -> list[tuple]:
    """(symbol, event_ts, close, high, low, volume, vwap, timespan) bars.

    AAA day1 bar 3  -> close  0.0  (zero close; its own return_1m = -1 while
                                    log_return_1m must stay NULL)
    BBB day1 bar 2  -> close -5.0  (negative close; non-positive ratios for the
                                    rows whose lag lands on it, at every horizon)
    CCC day2 bar 20 -> missing       (one-bar gap inside the session)
    """
    rows = []
    for sym in ("AAA", "BBB", "CCC"):
        for day in (DAY1, DAY2):
            for i in range(BARS_PER_SESSION):
                if sym == "CCC" and day == DAY2 and i == 20:
                    continue  # gap
                ts = datetime.fromisoformat(f"{day} 09:30:00") + timedelta(minutes=i)
                if sym == "AAA":
                    close = 100.0 + 0.05 * i + ((i * 7) % 5) * 0.02
                    if day == DAY1 and i == 3:
                        close = 0.0
                elif sym == "BBB":
                    close = 50.0 + 0.10 * i + ((i * 3) % 4) * 0.05
                    if day == DAY1 and i == 2:
                        close = -5.0
                else:
                    close = 20.0 + 0.02 * i
                rows.append((sym, ts, close, close + 1.0, close - 1.0,
                             1000.0, close, "minute"))
    return rows


def _run_sql(rows: list[tuple]) -> dict[tuple, dict]:
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE silver_ohlcv("
        "symbol VARCHAR, event_ts TIMESTAMP, close DOUBLE, high DOUBLE, "
        "low DOUBLE, volume DOUBLE, vwap DOUBLE, timespan VARCHAR)"
    )
    con.executemany("INSERT INTO silver_ohlcv VALUES (?,?,?,?,?,?,?,?)", rows)
    result = con.execute(_extract_feature_sql()).fetchall()
    cols = [d[0] for d in con.description]
    con.close()
    return {(r[0], r[1]): dict(zip(cols, r)) for r in result}


@pytest.fixture(scope="module")
def sql_rows() -> dict[tuple, dict]:
    return _run_sql(_synthetic_rows())


@pytest.fixture(scope="module")
def ref_rows() -> dict[tuple, dict]:
    return _reference([(r[0], r[1], r[2]) for r in _synthetic_rows()])


# ---------------------------------------------------------------------------
# 1. SQL text structure
# ---------------------------------------------------------------------------

def test_sql_text_has_guarded_log_returns():
    text = open(SQL_PATH, encoding="utf-8").read()
    assert "LN(" in text, "log returns must be computed with LN("
    for n in HORIZONS:
        guard = re.search(
            rf"CASE\s+WHEN\s+cr{n}\s*>\s+0\s+THEN\s+LN\(cr{n}\)", text
        )
        assert guard, (
            f"log_return_{n}m must be LN(cr{n}) guarded by CASE WHEN cr{n} > 0 "
            f"(non-positive ratio -> NULL, never NaN/-Infinity)"
        )


def test_log_return_windows_match_return_windows():
    """Same LAG offsets and the same PARTITION BY/ORDER BY as return_N."""
    text = open(SQL_PATH, encoding="utf-8").read()
    window = "OVER (PARTITION BY symbol, DATE(event_ts) ORDER BY event_ts)"
    for n in HORIZONS:
        r_expr = (
            f"close / NULLIF(LAG(close, {n})  {window}, 0) - 1 AS r{n}"
            if n < 10 else
            f"close / NULLIF(LAG(close, {n}) {window}, 0) - 1 AS r{n}"
        )
        cr_expr = (
            f"close / NULLIF(LAG(close, {n})  {window}, 0) AS cr{n}"
            if n < 10 else
            f"close / NULLIF(LAG(close, {n}) {window}, 0) AS cr{n}"
        )
        assert r_expr in text, f"return_{n}m window moved: {r_expr!r}"
        assert cr_expr in text, f"ratio for log_return_{n}m must use {cr_expr!r}"
    lag_lines = [
        ln for ln in text.splitlines()
        if "LAG(close" in ln and not ln.strip().startswith("--")
    ]
    assert lag_lines, "no LAG windows found"
    for ln in lag_lines:
        assert ln.count(
            "OVER (PARTITION BY symbol, DATE(event_ts) ORDER BY event_ts)"
        ) == 1, f"cross-day or mis-partitioned lag window: {ln.strip()!r}"


def test_final_select_projects_log_returns_next_to_returns():
    cols = _final_select_columns()
    idx_r = [cols.index(c) for c in RETURN_COLUMNS]
    idx_l = [cols.index(c) for c in LOG_RETURN_COLUMNS]
    assert idx_r == list(range(idx_r[0], idx_r[0] + 4)), "return_* must be contiguous"
    assert idx_l == [idx_r[-1] + 1 + i for i in range(4)], (
        "log_return_* must be projected as a block immediately after return_*"
    )


# ---------------------------------------------------------------------------
# 2. Behaviour vs the pure reference (real SQL, DuckDB)
# ---------------------------------------------------------------------------

def test_reference_matches_production_sql(sql_rows, ref_rows):
    assert set(sql_rows) == set(ref_rows)
    for key, expected in ref_rows.items():
        actual = sql_rows[key]
        for n in HORIZONS:
            for col in (f"return_{n}m", f"log_return_{n}m"):
                got, want = actual[col], expected[col]
                if want is None:
                    assert got is None, f"{key} {col}: expected NULL, got {got!r}"
                else:
                    assert got is not None, f"{key} {col}: expected {want!r}, got NULL"
                    assert got == pytest.approx(want, rel=1e-12, abs=1e-12), (
                        f"{key} {col}: {got!r} != {want!r}"
                    )


def test_log_return_is_log_one_plus_return(sql_rows, ref_rows):
    """Identity log_return_N == LN(1 + return_N) wherever log_return_N is defined."""
    for src_name, rows in (("sql", sql_rows), ("reference", ref_rows)):
        for key, rec in rows.items():
            for n in HORIZONS:
                ret, log = rec[f"return_{n}m"], rec[f"log_return_{n}m"]
                if log is not None:
                    assert ret is not None and ret > -1.0, f"{src_name} {key} n={n}"
                    assert log == pytest.approx(math.log1p(ret), rel=1e-9), (
                        f"{src_name} {key} log_return_{n}m != ln(1+return_{n}m)"
                    )
                else:
                    assert ret is None or ret <= -1.0, (
                        f"{src_name} {key} n={n}: return={ret!r} must force "
                        f"a non-NULL log return"
                    )


def test_day_boundary_rows_are_null(sql_rows):
    """First N bars of every (symbol, session day) have NULL returns/log returns,
    including the first bar of day 2 (no cross-session lag)."""
    per_partition: dict[tuple[str, str], list[tuple[datetime, dict]]] = {}
    for (sym, ts), rec in sql_rows.items():
        per_partition.setdefault((sym, ts.date().isoformat()), []).append((ts, rec))
    for (sym, day), rows in sorted(per_partition.items()):
        rows.sort(key=lambda x: x[0])
        for n in HORIZONS:
            for ts, rec in rows[:n]:
                assert rec[f"log_return_{n}m"] is None, (
                    f"{sym} {ts}: log_return_{n}m leaks across the session boundary"
                )
                assert rec[f"return_{n}m"] is None, f"{sym} {ts}: return_{n}m boundary"
            if day == DAY2:
                assert rows[0][1][f"log_return_{n}m"] is None, (
                    f"{sym} day2 first bar must not lag into day1 for n={n}"
                )


def test_non_positive_ratio_yields_null(sql_rows):
    """Zero/negative close and lags landing on them must give NULL log returns
    (never NaN / -Infinity); the zero-close bar keeps return_1m = -1."""
    key = lambda sym, day, i: (
        sym, datetime.fromisoformat(f"{day} 09:30:00") + timedelta(minutes=i)
    )

    # Zero close at AAA day1 bar 3: own log_return_1m NULL despite return_1m = -1.
    rec = sql_rows[key("AAA", DAY1, 3)]
    assert rec["return_1m"] == pytest.approx(-1.0)
    assert rec["log_return_1m"] is None
    # Rows whose lag lands on the zero close (NULLIF -> NULL ratio).
    for n in HORIZONS:
        assert sql_rows[key("AAA", DAY1, 3 + n)][f"return_{n}m"] is None
        assert sql_rows[key("AAA", DAY1, 3 + n)][f"log_return_{n}m"] is None

    # Negative close at BBB day1 bar 2: own row and every row whose lag lands
    # on it have non-positive ratios -> NULL log returns.
    rec = sql_rows[key("BBB", DAY1, 2)]
    assert rec["return_1m"] is not None and rec["return_1m"] < -1.0
    assert rec["log_return_1m"] is None
    for n in HORIZONS:
        assert sql_rows[key("BBB", DAY1, 2 + n)][f"log_return_{n}m"] is None, (
            f"negative lag close at n={n} must yield a NULL log return"
        )

    # Every populated value is finite (no NaN / -Infinity smuggled through).
    for (sym, ts), rec in sql_rows.items():
        for n in HORIZONS:
            val = rec[f"log_return_{n}m"]
            assert val is None or math.isfinite(val), f"{sym} {ts} n={n}: {val!r}"


# ---------------------------------------------------------------------------
# 3. Schema contract + metric definition + pipeline column-diff helper
# ---------------------------------------------------------------------------

def test_contract_requires_log_return_columns():
    from db.schema_contract import TABLE_COLUMNS

    required = set(TABLE_COLUMNS["gold_ohlcv_features"])
    assert set(LOG_RETURN_COLUMNS) <= required, (
        "gold_ohlcv_features contract must require the four log-return columns"
    )


def test_gold_sql_final_select_matches_contract():
    """Contract/consistency: the final SELECT projects exactly the contracted
    gold_ohlcv_features columns — dropping one fails here."""
    from db.schema_contract import TABLE_COLUMNS

    cols = _final_select_columns()
    assert len(cols) == len(set(cols)), f"duplicate projection: {cols}"
    assert set(cols) == set(TABLE_COLUMNS["gold_ohlcv_features"]), (
        f"gold_ohlcv_features SQL projection drifted from the schema contract: "
        f"missing={sorted(set(TABLE_COLUMNS['gold_ohlcv_features']) - set(cols))} "
        f"extra={sorted(set(cols) - set(TABLE_COLUMNS['gold_ohlcv_features']))}"
    )


def test_log_return_metric_definition():
    import yaml

    metrics = yaml.safe_load(open(METRICS_PATH, encoding="utf-8"))["metrics"]
    spec = metrics["log_return_N"]
    ret = metrics["return_N"]
    assert spec["formula"] == "LN(close[t] / NULLIF(close[t-N], 0))"
    assert spec["variants"] == LOG_RETURN_COLUMNS
    assert spec["source_table"] == ret["source_table"] == "gold_ohlcv_features"
    assert spec["price_adjustment"] == ret["price_adjustment"]
    assert spec.get("unadjusted_reason"), "unadjusted metrics need a documented reason"


def test_missing_gold_ohlcv_log_return_columns_diff():
    import pipelines.run_silver_gold as r

    assert r.missing_gold_ohlcv_log_return_columns([]) == LOG_RETURN_COLUMNS
    assert r.missing_gold_ohlcv_log_return_columns(
        ["symbol", "log_return_1m", "return_1m"]
    ) == LOG_RETURN_COLUMNS[1:]
    assert r.missing_gold_ohlcv_log_return_columns(
        ["log_return_30m", "log_return_15m", "log_return_5m", "log_return_1m"]
    ) == []
    assert r.missing_gold_ohlcv_log_return_columns(LOG_RETURN_COLUMNS) == []


class _FakeSpark:
    """Column-list stand-in: records SQL and applies ADD COLUMNS like Delta."""

    def __init__(self, columns):
        self.columns = list(columns)
        self.executed = []

    class _Table:
        def __init__(self, columns):
            self.columns = list(columns)

    def table(self, name):
        return self._Table(self.columns)

    def sql(self, stmt):
        self.executed.append(stmt)
        add = re.search(r"ADD COLUMNS \((.*)\)", stmt)
        if add:
            for item in add.group(1).split(","):
                self.columns.append(item.strip().split()[0])
        return []


def test_ensure_gold_ohlcv_log_return_columns_adds_only_missing_and_is_idempotent():
    import pipelines.run_silver_gold as r

    spark = _FakeSpark(["symbol", "feature_ts", "return_1m", "log_return_1m"])
    r.ensure_gold_ohlcv_log_return_columns(spark)
    assert len(spark.executed) == 1
    assert "ALTER TABLE" in spark.executed[0]
    assert "log_return_1m" not in spark.executed[0], "must not re-add existing columns"
    for col in ("log_return_5m", "log_return_15m", "log_return_30m"):
        assert col in spark.executed[0]
    assert set(spark.columns) >= set(LOG_RETURN_COLUMNS)

    # Idempotent: the second call on the now-complete schema is a no-op.
    r.ensure_gold_ohlcv_log_return_columns(spark)
    assert len(spark.executed) == 1

    # Nothing missing at all -> no ALTER.
    spark2 = _FakeSpark(LOG_RETURN_COLUMNS + ["symbol"])
    r.ensure_gold_ohlcv_log_return_columns(spark2)
    assert spark2.executed == []


def test_ensure_gold_ohlcv_log_return_columns_skips_unreadable_table():
    import pipelines.run_silver_gold as r

    class _Broken:
        def table(self, name):
            raise RuntimeError("TABLE_OR_VIEW_NOT_FOUND")

        def sql(self, stmt):  # pragma: no cover - must not be reached
            raise AssertionError("ALTER must not run when the table is unreadable")

    r.ensure_gold_ohlcv_log_return_columns(_Broken())  # must not raise


def test_ensure_gold_ohlcv_log_return_columns_runs_before_gold_step(monkeypatch):
    """Wiring: main() ALTERs the existing table before the gold_ohlcv_features
    MERGE step executes."""
    import sys
    import types

    try:
        import databricks.connect  # noqa: F401
    except ImportError:
        fake = types.ModuleType("databricks.connect")
        fake.DatabricksSession = object
        monkeypatch.setitem(sys.modules, "databricks.connect", fake)
        monkeypatch.delitem(sys.modules, "pipelines.run_silver_gold", raising=False)
    import pipelines.run_silver_gold as r

    spark = _FakeSpark(["symbol", "feature_ts"])
    calls: list[tuple] = []
    base_sql = spark.sql

    def sql_log(stmt):
        calls.append(("sql", stmt))
        return base_sql(stmt)

    def run_step_log(s, name, path, kind, syms):
        calls.append(("step", name))

    monkeypatch.setattr(spark, "sql", sql_log)
    monkeypatch.setattr(r, "get_spark", lambda: spark)
    monkeypatch.setattr(r, "register_universe", lambda s: ["AAA"])
    monkeypatch.setattr(r, "register_research_universe", lambda s: [])
    monkeypatch.setattr(r, "ensure_model_availability_columns", lambda s: None)
    monkeypatch.setattr(r, "run_step", run_step_log)
    monkeypatch.setattr(r, "run_availability_invariant", lambda s: 0)
    monkeypatch.setattr(r, "run_matrix_invariant", lambda s: 0)
    monkeypatch.setattr(r, "count", lambda s, t: 0)
    monkeypatch.setattr(sys, "argv", ["run_silver_gold.py", "--only", "gold"])
    monkeypatch.setattr(r, "SCHEMA", r.SCHEMA)
    monkeypatch.setattr(r, "FQN", r.FQN)

    r.main()

    assert "gold_ohlcv_features" in [c[1] for c in calls if c[0] == "step"]
    step_idx = calls.index(("step", "gold_ohlcv_features"))
    alter_idx = next(
        i for i, c in enumerate(calls) if c[0] == "sql" and "ADD COLUMNS" in c[1]
    )
    assert alter_idx < step_idx, (
        "ensure_gold_ohlcv_log_return_columns must ALTER the pre-deployed "
        "gold_ohlcv_features table before its MERGE step runs"
    )
    assert all(col in spark.columns for col in LOG_RETURN_COLUMNS)
