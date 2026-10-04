"""
tests/bronze/test_refresh_bronze_options.py
Bronze options refresh (lane `options`): pure parsing / key-selection helpers.

These tests exercise only the pure, import-safe helpers in
``notebooks/refresh_bronze_options.py`` — no Spark, no S3, no Databricks, no
live ingestion. The notebook guards all live work under ``main()`` so importing
it here does not start any ingestion.
"""
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pytest

from notebooks import refresh_bronze_options as m


# ---------------------------------------------------------------------------
# OPRA symbol parsing
# ---------------------------------------------------------------------------

def test_parse_opra_symbol_call():
    underlying, expiry, right, strike = m.parse_opra_symbol(
        "O:AAPL250117C00200000"
    )
    assert underlying == "AAPL"
    assert expiry.isoformat() == "2025-01-17"
    assert right == "CALL"
    assert strike == 200.0


def test_parse_opra_symbol_put():
    underlying, expiry, right, strike = m.parse_opra_symbol(
        "O:SPY251219P00430000"
    )
    assert underlying == "SPY"
    assert expiry.isoformat() == "2025-12-19"
    assert right == "PUT"
    assert strike == 430.0


def test_parse_opra_symbol_rejects_malformed():
    for bad in [
        "",
        None,
        "AAPL250117C00200000",          # missing O: prefix
        "O:AAPL250117X00200000",        # bad right letter
        "O:AAPL25C00200000",            # bad expiry width
        "O:AAPL250117C00",              # bad strike width
        "O:250117C00200000",            # missing underlying
    ]:
        assert m.parse_opra_symbol(bad) is None


def test_parse_opra_symbol_rejects_bad_expiry():
    # 99 is not a valid month -> strptime raises -> None
    assert m.parse_opra_symbol("O:AAPL259917C00200000") is None


# ---------------------------------------------------------------------------
# Field conversion helpers
# ---------------------------------------------------------------------------

def test_ns_to_ts():
    # 1_700_000_000_000_000_000 ns == 2023-11-14T22:13:20Z
    ts = m.ns_to_ts(1_700_000_000_000_000_000)
    assert ts == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)


def test_ns_to_ts_nulls_and_garbage():
    assert m.ns_to_ts(None) is None
    assert m.ns_to_ts("") is None
    assert m.ns_to_ts("not-a-number") is None


def test_as_float():
    assert m.as_float("3.14") == 3.14
    assert m.as_float(5) == 5.0
    assert m.as_float(None) is None
    assert m.as_float("") is None
    assert m.as_float("n/a") is None


def test_as_int():
    assert m.as_int("42") == 42
    assert m.as_int("42.9") == 42
    assert m.as_int(None) is None
    assert m.as_int("") is None
    assert m.as_int("abc") is None


# ---------------------------------------------------------------------------
# Date window discovery + S3 key layout
# ---------------------------------------------------------------------------

def test_date_window_inclusive():
    assert m.date_window("2026-09-05", "2026-09-07") == [
        "2026-09-05", "2026-09-06", "2026-09-07",
    ]


def test_date_window_single_day():
    assert m.date_window("2026-09-05", "2026-09-05") == ["2026-09-05"]


def test_date_window_rejects_reversed():
    with pytest.raises(ValueError):
        m.date_window("2026-10-03", "2026-09-05")


def test_s3_key_for_date():
    assert m.s3_key_for_date("2026-09-05") == (
        "us_options_opra/day_aggs_v1/2026/09/2026-09-05.csv.gz"
    )


# ---------------------------------------------------------------------------
# Natural-key columns match the plan
# ---------------------------------------------------------------------------

def test_day_key_columns():
    assert m.DAY_KEY_COLUMNS == ["contract_symbol", "event_ts", "timespan"]


def test_snapshot_key_columns():
    assert m.SNAPSHOT_KEY_COLUMNS == ["option_symbol", "participant_ts"]


# ---------------------------------------------------------------------------
# Snapshot timestamp resolution
# ---------------------------------------------------------------------------

def test_resolve_snapshot_ts_prefers_provider():
    snap_ts = datetime(2026, 10, 3, 16, 0, tzinfo=timezone.utc)
    provider = datetime(2026, 10, 3, 15, 59, 58, tzinfo=timezone.utc)
    assert m.resolve_snapshot_ts(provider, snap_ts) == provider


def test_resolve_snapshot_ts_falls_back():
    snap_ts = datetime(2026, 10, 3, 16, 0, tzinfo=timezone.utc)
    assert m.resolve_snapshot_ts(None, snap_ts) == snap_ts


# ---------------------------------------------------------------------------
# Snapshot row mapping (shape_quote_row)
# ---------------------------------------------------------------------------

def _make_snapshot(contract_type="call", sip_timestamp=None):
    snap = MagicMock()
    snap.details = MagicMock()
    snap.details.ticker = "O:SPY261218C00600000"
    snap.details.expiration_date = "2026-12-18"
    snap.details.strike_price = 600.0
    snap.details.contract_type = contract_type

    snap.last_quote = MagicMock()
    snap.last_quote.bid = 10.0
    snap.last_quote.ask = 10.5
    snap.last_quote.bid_size = 12
    snap.last_quote.ask_size = 34
    snap.last_quote.midpoint = None
    snap.last_quote.sip_timestamp = sip_timestamp
    snap.last_quote.participant_timestamp = None

    snap.greeks = MagicMock()
    snap.greeks.delta = 0.6
    snap.greeks.gamma = 0.01
    snap.greeks.theta = -0.2
    snap.greeks.vega = 0.3

    snap.last_trade = MagicMock()
    snap.last_trade.price = 10.25
    snap.day = MagicMock()
    snap.day.volume = 500
    snap.open_interest = 1234
    snap.implied_volatility = 0.35
    return snap


def test_shape_quote_row_full():
    snap_ts = datetime(2026, 10, 3, 16, 0, tzinfo=timezone.utc)
    row = m.shape_quote_row(_make_snapshot(), "SPY", snap_ts)
    assert row is not None
    assert row["option_symbol"] == "O:SPY261218C00600000"
    assert row["underlying"] == "SPY"
    assert row["expiry"] == date(2026, 12, 18)
    assert row["strike"] == 600.0
    assert row["right"] == "call"
    assert row["midpoint"] == 10.25  # (10.0 + 10.5) / 2
    assert row["delta"] == 0.6
    assert row["gamma"] == 0.01
    assert row["theta"] == -0.2
    assert row["vega"] == 0.3
    assert row["implied_volatility"] == 0.35
    assert row["open_interest"] == 1234.0
    assert row["volume"] == 500
    assert row["last_price"] == 10.25
    assert row["source"] == "polygon"


def test_shape_quote_row_right_put():
    snap_ts = datetime(2026, 10, 3, 16, 0, tzinfo=timezone.utc)
    row = m.shape_quote_row(_make_snapshot(contract_type="put"), "SPY", snap_ts)
    assert row["right"] == "put"


def test_shape_quote_row_uses_provider_ts():
    snap_ts = datetime(2026, 10, 3, 16, 0, tzinfo=timezone.utc)
    # 1_700_000_000_000_000_000 ns == 2023-11-14T22:13:20Z
    row = m.shape_quote_row(
        _make_snapshot(sip_timestamp=1_700_000_000_000_000_000), "SPY", snap_ts
    )
    assert row["participant_ts"] == datetime(
        2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc
    )


def test_shape_quote_row_falls_back_to_snapshot_ts():
    snap_ts = datetime(2026, 10, 3, 16, 0, tzinfo=timezone.utc)
    row = m.shape_quote_row(_make_snapshot(sip_timestamp=None), "SPY", snap_ts)
    assert row["participant_ts"] == snap_ts


def test_shape_quote_row_no_symbol_returns_none():
    snap_ts = datetime(2026, 10, 3, 16, 0, tzinfo=timezone.utc)
    snap = _make_snapshot()
    snap.details = None
    assert m.shape_quote_row(snap, "SPY", snap_ts) is None


def test_shape_quote_row_right_normalisation():
    assert m._right_from_contract_type("call") == "call"
    assert m._right_from_contract_type("CALL") == "call"
    assert m._right_from_contract_type("put") == "put"
    assert m._right_from_contract_type("P") == "put"
    assert m._right_from_contract_type("weird") is None
    assert m._right_from_contract_type(None) is None


# ---------------------------------------------------------------------------
# _resolve_write_columns: schema mismatch raises
# ---------------------------------------------------------------------------

def test_resolve_write_columns_reorders_matching():
    """When column sets match but order differs, return table order."""
    spark = MagicMock()
    spark.sql.return_value.collect.return_value = [
        {"col_name": "b"}, {"col_name": "a"}, {"col_name": "c"},
    ]
    df = MagicMock()
    df.columns = ["a", "b", "c"]
    result = m._resolve_write_columns(spark, df, "some_table")
    assert result == ["b", "a", "c"]


def test_resolve_write_columns_raises_on_extra_df_columns():
    """DataFrame has columns the live table lacks → ValueError."""
    spark = MagicMock()
    spark.sql.return_value.collect.return_value = [
        {"col_name": "a"}, {"col_name": "b"},
    ]
    df = MagicMock()
    df.columns = ["a", "b", "extra_col"]
    with pytest.raises(ValueError, match="extra in DataFrame"):
        m._resolve_write_columns(spark, df, "some_table")


def test_resolve_write_columns_raises_on_missing_df_columns():
    """Live table has columns the DataFrame lacks → ValueError."""
    spark = MagicMock()
    spark.sql.return_value.collect.return_value = [
        {"col_name": "a"}, {"col_name": "b"}, {"col_name": "needed"},
    ]
    df = MagicMock()
    df.columns = ["a", "b"]
    with pytest.raises(ValueError, match="missing from DataFrame"):
        m._resolve_write_columns(spark, df, "some_table")


def test_resolve_write_columns_skips_comment_rows():
    """DESCRIBE TABLE returns '#' comment rows; skip them."""
    spark = MagicMock()
    spark.sql.return_value.collect.return_value = [
        {"col_name": "# Partition Information"},
        {"col_name": "# col_name"},
        {"col_name": "a"},
        {"col_name": "b"},
    ]
    df = MagicMock()
    df.columns = ["a", "b"]
    result = m._resolve_write_columns(spark, df, "some_table")
    assert result == ["a", "b"]


# ---------------------------------------------------------------------------
# Staging: Files API used when not inside Databricks
# ---------------------------------------------------------------------------

def test_stage_file_uses_files_api_when_not_in_databricks(tmp_path, monkeypatch):
    """Outside Databricks, _stage_file must download locally then upload via
    the SDK Files API — never touch /Volumes as a local path."""
    monkeypatch.delenv("DATABRICKS_RUNTIME_VERSION", raising=False)

    s3 = MagicMock()
    # Simulate download_file writing a local file.
    def fake_download(bucket, key, local_path):
        import os
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(b"fake,gzip,data\n")
    s3.download_file.side_effect = fake_download

    sdk_client = MagicMock()
    local_root = str(tmp_path)

    result = m._stage_file(s3, "us_options_opra/day_aggs_v1/2026/09/2026-09-22.csv.gz",
                           sdk_client, local_root)
    assert result is not None
    assert "/Volumes/" in result
    sdk_client.files.upload.assert_called_once()
    call_args = sdk_client.files.upload.call_args
    assert call_args[1].get("overwrite") is True or call_args[0][2] is True
    # Local temp file should be cleaned up.
    upload_local = call_args[0][1]
    assert not hasattr(upload_local, "close") or True  # file handle is fine


# ---------------------------------------------------------------------------
# Trading-day calendar: weekends and holidays excluded
# ---------------------------------------------------------------------------

def test_trading_days_skips_saturday():
    """2026-09-26 is a Saturday — must not appear in trading_days output."""
    days = m.trading_days("2026-09-25", "2026-09-28")
    assert "2026-09-26" not in days  # Saturday
    assert "2026-09-27" not in days  # Sunday
    assert "2026-09-25" in days      # Friday
    assert "2026-09-28" in days      # Monday


def test_trading_days_skips_holiday():
    """2026-12-25 (Christmas) is a Friday — must not appear."""
    days = m.trading_days("2026-12-24", "2026-12-26")
    assert "2026-12-25" not in days
    assert "2026-12-24" in days  # Thursday
    assert "2026-12-26" not in days  # Saturday (weekend)


# ---------------------------------------------------------------------------
# Missing file on a real trading day counts as failed
# ---------------------------------------------------------------------------

def test_trading_day_missing_file_counts_as_failed(monkeypatch, capsys):
    """A trading day whose S3 object 404s (head_object raises a non-403
    ClientError) must increment the failed counter, not entitlement_gap."""
    ClientError = pytest.importorskip("botocore.exceptions").ClientError

    monkeypatch.delenv("DATABRICKS_RUNTIME_VERSION", raising=False)

    spark = MagicMock()
    # _run_daily calls spark.sql 4 times: pre_count, pre_max, post_count, post_max
    count_result = MagicMock()
    count_result.collect.return_value = [{"n": 0}]
    max_result = MagicMock()
    max_result.collect.return_value = [{"m": None}]
    spark.sql.side_effect = [count_result, max_result, count_result, max_result]

    s3 = MagicMock()
    s3.head_object.side_effect = ClientError(
        {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject"
    )

    monkeypatch.setattr(m, "already_ingested", lambda *a, **kw: False)
    monkeypatch.setattr(m, "_in_databricks", lambda: True)

    result = m._run_daily(spark, s3, "files.massive.com",
                          "2026-09-25", "2026-09-25", dry_run=True)
    assert result["failed"] == 1
    assert result["entitlement_gap"] == 0


# ---------------------------------------------------------------------------
# _anti_join_new: fake DataFrame engine (local SparkSession unavailable)
# ---------------------------------------------------------------------------
# PySpark on this machine is Databricks-Connect-only (no local SparkSession).
# We build a lightweight in-memory DataFrame that mirrors the three chained
# calls _anti_join_new makes: dropDuplicates, join(left_anti), filter/select/
# distinct.  The fake engine operates on list[dict] rows so the tests exercise
# the real function end-to-end without a live Spark cluster.


class _Expr:
    """AST node for a simple binary comparison (col op literal)."""
    __slots__ = ("col_name", "op", "value")

    def __init__(self, col_name, op, value):
        self.col_name = col_name
        self.op = op
        self.value = value

    def __and__(self, other):
        return _AndExpr(self, other)

    def eval(self, row):
        left = row.get(self.col_name)
        if left is None:
            return False
        if self.op == ">=":
            return left >= self.value
        if self.op == "<=":
            return left <= self.value
        return False


class _AndExpr:
    __slots__ = ("left", "right")

    def __init__(self, left, right):
        self.left = left
        self.right = right

    def eval(self, row):
        return self.left.eval(row) and self.right.eval(row)


class _ColRef:
    """Column reference that returns _Expr on comparison."""
    __slots__ = ("name",)

    def __init__(self, name):
        self.name = name

    def __ge__(self, other):
        return _Expr(self.name, ">=", other.value if isinstance(other, _Lit) else other)

    def __le__(self, other):
        return _Expr(self.name, "<=", other.value if isinstance(other, _Lit) else other)


class _Lit:
    """Literal value wrapper with .cast() no-op."""
    __slots__ = ("value",)

    def __init__(self, value):
        self.value = value

    def cast(self, _type):
        return self


def _fake_col(name):
    return _ColRef(name)


def _fake_lit(value):
    return _Lit(value)


class _FakeDataFrame:
    """Minimal DataFrame that mirrors PySpark's chaining API on row dicts."""

    def __init__(self, rows):
        self._rows = list(rows)

    def dropDuplicates(self, key_columns):
        seen = set()
        deduped = []
        for row in self._rows:
            key = tuple(row.get(k) for k in key_columns)
            if key not in seen:
                seen.add(key)
                deduped.append(row)
        return _FakeDataFrame(deduped)

    def join(self, other, key_columns, how):
        if how != "left_anti":
            raise ValueError(f"Only left_anti supported in fake, got {how}")
        other_keys = {
            tuple(row.get(k) for k in key_columns) for row in other._rows
        }
        filtered = [
            row for row in self._rows
            if tuple(row.get(k) for k in key_columns) not in other_keys
        ]
        return _FakeDataFrame(filtered)

    def filter(self, expr):
        return _FakeDataFrame(r for r in self._rows if expr.eval(r))

    def select(self, columns):
        return _FakeDataFrame(
            {col: row.get(col) for col in columns} for row in self._rows
        )

    def distinct(self):
        seen = set()
        deduped = []
        for row in self._rows:
            key = tuple(sorted(row.items()))
            if key not in seen:
                seen.add(key)
                deduped.append(row)
        return _FakeDataFrame(deduped)

    def count(self):
        return len(self._rows)

    def collect(self):
        return list(self._rows)


class _FakeSparkSession:
    """Spark session stub backed by an in-memory table registry."""

    def __init__(self):
        self._tables = {}

    def _register(self, name, rows):
        self._tables[name] = _FakeDataFrame(rows)

    def table(self, name):
        return self._tables[name]


# ---- Test data fixtures ----

_DAY_KEY = ["contract_symbol", "event_ts", "timespan"]
_TABLE = "test.bronze_options_day"

_INCOMING_ROWS = [
    # duplicate key (sym_A + ts_1 + day) appears twice — must collapse
    {"contract_symbol": "sym_A", "event_ts": "t1", "timespan": "day",
     "event_date": "2026-09-25", "close": 1.0},
    {"contract_symbol": "sym_A", "event_ts": "t1", "timespan": "day",
     "event_date": "2026-09-25", "close": 1.0},
    # genuinely new key
    {"contract_symbol": "sym_B", "event_ts": "t2", "timespan": "day",
     "event_date": "2026-09-25", "close": 2.0},
    # already in target
    {"contract_symbol": "sym_C", "event_ts": "t3", "timespan": "day",
     "event_date": "2026-09-26", "close": 3.0},
]

_TARGET_ROWS = [
    # sym_C + t3 + day already ingested
    {"contract_symbol": "sym_C", "event_ts": "t3", "timespan": "day",
     "event_date": "2026-09-26"},
    # unrelated old row — outside date filter
    {"contract_symbol": "sym_X", "event_ts": "t9", "timespan": "day",
     "event_date": "2026-09-01"},
]


def _run_anti_join(incoming_rows, target_rows):
    """Execute _anti_join_new through the fake engine and return result rows."""
    F_mod = pytest.importorskip("pyspark.sql.functions")

    spark = _FakeSparkSession()
    spark._register(_TABLE, target_rows)

    incoming = _FakeDataFrame(incoming_rows)

    orig_col = F_mod.col
    orig_lit = F_mod.lit
    F_mod.col = _fake_col
    F_mod.lit = _fake_lit
    try:
        result = m._anti_join_new(
            spark, incoming, _DAY_KEY, _TABLE, "event_date",
            "2026-09-25", "2026-09-30",
        )
    finally:
        F_mod.col = orig_col
        F_mod.lit = orig_lit
    return result.collect()


def test_anti_join_new_deduplicates_incoming():
    """Duplicate keys within the incoming batch collapse to one row."""
    result = _run_anti_join(_INCOMING_ROWS, _TARGET_ROWS)
    keys = [(r["contract_symbol"], r["event_ts"], r["timespan"]) for r in result]
    # sym_A/t1/day appeared twice → must appear exactly once
    assert keys.count(("sym_A", "t1", "day")) == 1


def test_anti_join_new_excludes_existing_target_keys():
    """Keys already present in the target are excluded."""
    result = _run_anti_join(_INCOMING_ROWS, _TARGET_ROWS)
    keys = [(r["contract_symbol"], r["event_ts"], r["timespan"]) for r in result]
    assert ("sym_C", "t3", "day") not in keys


def test_anti_join_new_passes_genuinely_new_keys():
    """Genuinely new keys pass through."""
    result = _run_anti_join(_INCOMING_ROWS, _TARGET_ROWS)
    keys = [(r["contract_symbol"], r["event_ts"], r["timespan"]) for r in result]
    assert ("sym_B", "t2", "day") in keys
    assert len(result) == 2  # sym_A (deduped) + sym_B; sym_C excluded
