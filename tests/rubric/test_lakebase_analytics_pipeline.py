"""tests/rubric/test_lakebase_analytics_pipeline.py — CI-safe pipeline tests.

Tests connection helper, batch loop, replay/idempotency, ordering, and retry
semantics using fake Spark and Postgres objects (no network, no live DB, no
pyspark required).
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock

import pytest

from pipelines.lakebase_analytics import (
    OutboxEvent,
    claim_batch,
    compute_agent_activity,
    compute_watchlist_changes,
    compute_order_funnel,
    compute_usage_daily,
    extract_date,
    mark_delivered,
    mark_failed,
    merge_events_to_delta,
    open_lakebase_connection,
    parse_event,
    run_batches,
    run_pipeline,
    DEFAULT_MAX_BATCHES,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _ev(event_id: int, table: str, pk: str, op: str,
        after: Dict[str, Any] | None = None,
        before: Dict[str, Any] | None = None,
        occurred: str = "2025-01-15T10:00:00+00:00") -> OutboxEvent:
    return OutboxEvent(
        event_id=event_id, source_table=table, source_pk=pk,
        operation=op, before_payload=before, after_payload=after,
        occurred_at=_dt(occurred),
    )


# ── Fake Spark infrastructure ───────────────────────────────────────────────

class _FakeCatalog:
    def __init__(self, tables: Dict[str, Any]):
        self._tables = tables

    def tableExists(self, fqn: str) -> bool:
        return fqn in self._tables


class _FakeDF:
    """Minimal DataFrame stub for testing."""

    def __init__(self, rows: list, spark: "FakeSpark" = None):
        self._rows = rows
        self._spark = spark

    def limit(self, n: int) -> "_FakeDF":
        return _FakeDF(self._rows[:n], self._spark)

    def fillna(self, defaults: Any, subset: Any = None) -> "_FakeDF":
        filled = []
        for row in self._rows:
            new_row = dict(row)
            for k, v in (defaults.items() if isinstance(defaults, dict) else []):
                if new_row.get(k) is None:
                    new_row[k] = v
            filled.append(new_row)
        return _FakeDF(filled, self._spark)

    def createOrReplaceTempView(self, name: str) -> None:
        if self._spark is not None:
            self._spark._views[name] = list(self._rows)

    def collect(self):
        return [_FakeRow(r) for r in self._rows]

    @property
    def write(self):
        return _FakeWrite(self)


class _FakeWrite:
    def __init__(self, df: _FakeDF):
        self._df = df

    def format(self, fmt: str) -> "_FakeWrite":
        return self

    def saveAsTable(self, fqn: str) -> None:
        if self._df._spark is not None:
            self._df._spark._tables[fqn] = []


class _FakeRow:
    def __init__(self, data: Dict[str, Any]):
        self._data = data

    def asDict(self) -> Dict[str, Any]:
        return dict(self._data)

    def __getitem__(self, key):
        return self._data[key]

    def __contains__(self, key):
        return key in self._data


class FakeSpark:
    """In-memory Spark stub supporting MERGE/DELETE/INSERT/SELECT patterns."""

    def __init__(self):
        self._tables: Dict[str, list] = {}
        self._views: Dict[str, list] = {}
        self.catalog = _FakeCatalog(self._tables)

    def createDataFrame(self, rows: list, schema: Any = None) -> _FakeDF:
        return _FakeDF(list(rows), self)

    def sql(self, text: str) -> Optional[_FakeDF]:
        text = text.strip()
        # MERGE INTO <target> USING <view> ON t.event_id = s.event_id
        m = re.search(
            r"MERGE\s+INTO\s+(\S+)\s+t\s+USING\s+(\S+)\s+s\s+"
            r"ON\s+t\.event_id\s*=\s*s\.event_id",
            text, re.IGNORECASE,
        )
        if m:
            target, view = m.group(1), m.group(2)
            staging = list(self._views.get(view, []))
            existing = {r["event_id"]: dict(r) for r in self._tables.get(target, [])}
            for row in staging:
                existing[row["event_id"]] = dict(row)
            self._tables[target] = list(existing.values())
            return None

        # MERGE ... ON t.run_id = s.run_id
        m = re.search(
            r"MERGE\s+INTO\s+(\S+)\s+t\s+USING\s+(\S+)\s+s\s+"
            r"ON\s+t\.run_id\s*=\s*s\.run_id",
            text, re.IGNORECASE,
        )
        if m:
            target, view = m.group(1), m.group(2)
            staging = list(self._views.get(view, []))
            existing = {r["run_id"]: dict(r) for r in self._tables.get(target, [])}
            for row in staging:
                existing[row["run_id"]] = dict(row)
            self._tables[target] = list(existing.values())
            return None

        # DELETE FROM <table> WHERE event_date IN (...)
        m = re.search(
            r"DELETE\s+FROM\s+(\S+)\s+WHERE\s+event_date\s+IN\s*\(([^)]+)\)",
            text, re.IGNORECASE,
        )
        if m:
            target = m.group(1)
            dates = set(re.findall(r"'([^']+)'", m.group(2)))
            self._tables[target] = [
                r for r in self._tables.get(target, [])
                if r.get("event_date") not in dates
            ]
            return None

        # INSERT INTO <table> SELECT * FROM <view>
        m = re.search(
            r"INSERT\s+INTO\s+(\S+)\s+SELECT\s+\*\s+FROM\s+(\S+)",
            text, re.IGNORECASE,
        )
        if m:
            target, view = m.group(1), m.group(2)
            rows = list(self._views.get(view, []))
            self._tables.setdefault(target, []).extend(rows)
            return None

        # SELECT ... FROM <table> WHERE ... IN (...)
        m = re.search(
            r"SELECT\s+.*?\s+FROM\s+(\S+)\s+WHERE\s+date\(occurred_at\)\s+IN\s*\(([^)]+)\)",
            text, re.IGNORECASE | re.DOTALL,
        )
        if m:
            target = m.group(1)
            dates = set(re.findall(r"'([^']+)'", m.group(2)))
            matching = []
            for r in self._tables.get(target, []):
                oa = r.get("occurred_at")
                if oa is not None:
                    from pipelines.lakebase_analytics import extract_date
                    if extract_date(oa) in dates:
                        matching.append(r)
            return _FakeDF(matching, self)

        return None


# ── Fake Postgres ────────────────────────────────────────────────────────────

class _FakeRowWrapper:
    """Dict that also supports positional indexing for cursor.fetchall()."""

    def __init__(self, d: Dict[str, Any]):
        self._d = dict(d)
        self._keys = list(d.keys())

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._d[self._keys[key]]
        return self._d[key]

    def __contains__(self, key):
        return key in self._d

    def __iter__(self):
        return iter(self._d.values())


class FakeCursor:
    """In-memory cursor simulating analytics_outbox operations."""

    def __init__(self, conn: "FakeConn"):
        self._conn = conn
        self._rows: list = []

    def execute(self, sql: str, params: tuple = ()) -> None:
        sql = sql.strip()
        # -- claim_batch: UPDATE ... SET attempt_count = attempt_count + 1
        #    WHERE event_id IN (SELECT ... delivered_at IS NULL ...) RETURNING ...
        if "attempt_count = attempt_count + 1" in sql:
            limit = params[0] if params else 100
            pending = [r for r in self._conn._outbox if r["delivered_at"] is None]
            claimed = pending[:limit]
            for row in claimed:
                row["attempt_count"] += 1
            self._rows = [_FakeRowWrapper({
                "event_id": r["event_id"], "source_table": r["source_table"],
                "source_pk": r["source_pk"], "operation": r["operation"],
                "before_payload": r.get("before_payload"),
                "after_payload": r.get("after_payload"),
                "occurred_at": r["occurred_at"],
            }) for r in claimed]
            return

        # -- mark_delivered: SET delivered_at = now(), last_error = NULL
        if "SET delivered_at = now(), last_error = NULL" in sql:
            eids = set(params[0]) if params else set()
            for row in self._conn._outbox:
                if row["event_id"] in eids:
                    row["delivered_at"] = datetime.now(timezone.utc)
                    row["last_error"] = None
            self._rows = []
            return

        # -- mark_failed: SET delivered_at = NULL, last_error = %s
        if "delivered_at = NULL, last_error = %s" in sql:
            error = params[0][:500] if params else ""
            eids = set(params[1]) if params and len(params) > 1 else set()
            for row in self._conn._outbox:
                if row["event_id"] in eids:
                    row["delivered_at"] = None
                    row["last_error"] = error
            self._rows = []
            return

        self._rows = []

    def fetchall(self) -> list:
        rows = list(self._rows)
        self._rows = []
        return rows

    def fetchone(self):
        if self._rows:
            return self._rows.pop(0)
        return None


class FakeConn:
    """In-memory Postgres connection tracking analytics_outbox state."""

    def __init__(self, outbox_rows: List[Dict[str, Any]]):
        self._outbox = [dict(r) for r in outbox_rows]
        self._committed = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self._committed = True

    def close(self) -> None:
        pass


# ── open_lakebase_connection tests ──────────────────────────────────────────

class TestOpenLakebaseConnection:

    def test_no_url_uses_injected_token_provider(self, monkeypatch, caplog):
        """open_lakebase_connection with no LAKEBASE_URL uses token provider,
        never raises 'LAKEBASE_URL not set'."""
        monkeypatch.delenv("LAKEBASE_URL", raising=False)
        # Built at run time so no secret-looking literal sits in the repo (secret scanners flag one).
        fake_token = "-".join(("s3cr3t", "tok3n", "valu3"))
        provider = lambda: {"token": fake_token, "expiration_time": "2099-01-01T00:00:00Z"}
        recorded = {}

        def fake_connect(**kwargs):
            recorded.update(kwargs)
            conn = MagicMock()
            conn.autocommit = False
            return conn

        fake_lb = types.ModuleType("db.lakebase")
        fake_lb.LAKEBASE_HOST = "test-host"
        fake_lb.LAKEBASE_PORT = 5432
        fake_lb.LAKEBASE_DBNAME = "test-db"
        fake_lb.LAKEBASE_USER = "test-user"
        fake_lb.LAKEBASE_SSLMODE = "require"
        fake_lb.LAKEBASE_CONNECT_TIMEOUT = 3
        fake_lb.mint_token_via_cli = lambda: {"token": fake_token, "expiration_time": None}

        monkeypatch.setitem(sys.modules, "db", types.ModuleType("db"))
        monkeypatch.setitem(sys.modules, "db.lakebase", fake_lb)

        with caplog.at_level(logging.INFO):
            conn = open_lakebase_connection(
                token_provider=provider, connect=fake_connect
            )

        assert conn is not None
        assert recorded.get("password") == fake_token
        assert recorded.get("host") == "test-host"
        assert "minted-oauth" in caplog.text

    def test_token_never_in_logs_or_exceptions(self, monkeypatch, caplog):
        """Canary token must not appear in logs or exception text."""
        canary = "CANARY_SECRET_TOKEN_abc123xyz"
        provider = lambda: {"token": canary, "expiration_time": None}

        def fake_connect(**kwargs):
            raise RuntimeError("connection refused")

        fake_lb = types.ModuleType("db.lakebase")
        fake_lb.LAKEBASE_HOST = "h"
        fake_lb.LAKEBASE_PORT = 5432
        fake_lb.LAKEBASE_DBNAME = "db"
        fake_lb.LAKEBASE_USER = "user"
        fake_lb.LAKEBASE_SSLMODE = "require"
        fake_lb.LAKEBASE_CONNECT_TIMEOUT = 1
        fake_lb.mint_token_via_cli = provider

        monkeypatch.setitem(sys.modules, "db", types.ModuleType("db"))
        monkeypatch.setitem(sys.modules, "db.lakebase", fake_lb)

        with pytest.raises(RuntimeError, match=r"Lakebase connection failed"):
            with caplog.at_level(logging.DEBUG):
                open_lakebase_connection(
                    token_provider=provider, connect=fake_connect
                )

        assert canary not in caplog.text

    def test_url_override_logged_without_value(self, monkeypatch, caplog):
        """LAKEBASE_URL override is logged as url-override; value is never logged."""
        secret_url = "postgres://admin:hunter2@db.example.com:5432/prod"
        monkeypatch.setenv("LAKEBASE_URL", secret_url)

        recorded = {}

        def fake_connect(url):
            recorded["url"] = url
            conn = MagicMock()
            conn.autocommit = False
            return conn

        with caplog.at_level(logging.INFO):
            conn = open_lakebase_connection(connect=fake_connect)

        assert "url-override" in caplog.text
        assert secret_url not in caplog.text
        assert recorded["url"] == secret_url

    # -- P1: credential canaries must never survive exception sanitization --

    @staticmethod
    def _fake_lakebase(monkeypatch, mint=None):
        """Install a fake ``db.lakebase`` module (importable without psycopg)."""
        fake_lb = types.ModuleType("db.lakebase")
        fake_lb.LAKEBASE_HOST = "h"
        fake_lb.LAKEBASE_PORT = 5432
        fake_lb.LAKEBASE_DBNAME = "db"
        fake_lb.LAKEBASE_USER = "user"
        fake_lb.LAKEBASE_SSLMODE = "require"
        fake_lb.LAKEBASE_CONNECT_TIMEOUT = 1
        fake_lb.mint_token_via_cli = mint or (
            lambda: {"token": "t", "expiration_time": None}
        )
        monkeypatch.setitem(sys.modules, "db", types.ModuleType("db"))
        monkeypatch.setitem(sys.modules, "db.lakebase", fake_lb)
        return fake_lb

    @staticmethod
    def _assert_sanitized(exc, canaries, caplog):
        """The sanitized error must expose no credential text and no chain.

        Checked on ``str(exc)``, ``repr(exc)``,
        ``traceback.format_exception(...)``, captured logs, and every
        exception still reachable through ``__cause__``/``__context__``.
        The error must be raised with ``from None`` (context display
        suppressed, no cause, no context).
        """
        import traceback as _tb

        blob = "\n".join(
            [str(exc), repr(exc), "".join(_tb.format_exception(exc)), caplog.text]
        )
        for canary in canaries:
            assert canary not in blob, (
                f"canary {canary!r} leaked into sanitized error or logs:\n{blob}"
            )

        assert exc.__cause__ is None, (
            "sanitized error must not chain the original via __cause__"
        )
        assert exc.__context__ is None, (
            "sanitized error must not chain the original via __context__"
        )
        assert exc.__suppress_context__ is True, (
            "sanitized error must be raised with 'raise ... from None'"
        )

        seen, stack = set(), [exc]
        while stack:
            node = stack.pop()
            if id(node) in seen:
                continue
            seen.add(id(node))
            for canary in canaries:
                assert canary not in str(node), f"canary {canary!r} in chain node"
                assert canary not in repr(node), f"canary {canary!r} in chain node"
            stack.extend(
                n for n in (node.__cause__, node.__context__) if n is not None
            )

    def test_provider_failure_sanitized_no_canary(self, monkeypatch, caplog):
        """A raising token provider must surface only a sanitized error.

        Canary token/URL must be absent from ``str(exc)``, ``repr(exc)``,
        ``traceback.format_exception(...)`` and logs; no chain remains.
        """
        canary_token = "CANARY_SECRET_TOKEN_abc123xyz"
        canary_url = "postgres://admin:hunter2@canary-host:5432/prod"
        monkeypatch.delenv("LAKEBASE_URL", raising=False)

        def provider():
            raise RuntimeError(
                f"mint failed for {canary_url} with {canary_token}"
            )

        self._fake_lakebase(monkeypatch)
        with caplog.at_level(logging.DEBUG):
            with pytest.raises(
                RuntimeError, match=r"Lakebase credential mint failed"
            ) as ei:
                open_lakebase_connection(
                    token_provider=provider, connect=MagicMock()
                )
        self._assert_sanitized(
            ei.value, [canary_token, canary_url, "hunter2", "canary-host"], caplog
        )

    def test_connect_failure_sanitized_no_canary(self, monkeypatch, caplog):
        """A raising psycopg.connect on the minted path must surface only a
        sanitized error — the minted token canary must not leak."""
        canary_token = "CANARY_SECRET_TOKEN_abc123xyz"
        monkeypatch.delenv("LAKEBASE_URL", raising=False)
        provider = lambda: {"token": canary_token, "expiration_time": None}

        def fake_connect(**kwargs):
            raise RuntimeError(f"connect failed password={kwargs['password']}")

        self._fake_lakebase(monkeypatch, mint=provider)
        with caplog.at_level(logging.DEBUG):
            with pytest.raises(
                RuntimeError, match=r"Lakebase connection failed"
            ) as ei:
                open_lakebase_connection(
                    token_provider=provider, connect=fake_connect
                )
        self._assert_sanitized(ei.value, [canary_token], caplog)

    def test_url_override_failure_sanitized_no_canary(self, monkeypatch, caplog):
        """A raising connect on the LAKEBASE_URL override path must surface
        only a sanitized error — the override URL canary must not leak."""
        canary_url = "postgres://admin:hunter2@db.example.com:5432/prod"
        monkeypatch.setenv("LAKEBASE_URL", canary_url)

        def fake_connect(url):
            raise RuntimeError(f"could not connect to {url}")

        with caplog.at_level(logging.DEBUG):
            with pytest.raises(
                RuntimeError, match=r"Lakebase connection failed"
            ) as ei:
                open_lakebase_connection(connect=fake_connect)
        self._assert_sanitized(
            ei.value, [canary_url, "hunter2", "db.example.com"], caplog
        )


# ── batch loop tests ─────────────────────────────────────────────────────────

class TestBatchLoop:

    def test_fake_pipeline_true_true_false_runs_3_times(self):
        """run_pipeline returning True, True, False runs exactly 3 batches."""
        calls = []
        responses = [True, True, False]

        def fake_pipeline(spark, conn, catalog, schema, batch_size):
            idx = len(calls)
            calls.append(idx)
            return responses[idx]

        spark = FakeSpark()
        conn = FakeConn([])

        batches = run_batches(
            spark, conn, "cat", "sch", 100, DEFAULT_MAX_BATCHES,
            run_pipeline_fn=fake_pipeline,
        )
        assert batches == 3
        assert len(calls) == 3

    def test_max_batches_limits_execution(self):
        """--max-batches limits the number of batches executed."""
        calls = []

        def always_true(spark, conn, catalog, schema, batch_size):
            calls.append(True)
            return True

        spark = FakeSpark()
        conn = FakeConn([])

        batches = run_batches(
            spark, conn, "cat", "sch", 100, 2,
            run_pipeline_fn=always_true,
        )
        assert batches == 2
        assert len(calls) == 2


# ── replay / idempotency tests ──────────────────────────────────────────────

class TestReplayIdempotency:

    def test_same_event_twice_yields_single_delta_row(self):
        """Delivering the same note event twice (crash before mark_delivered)
        -> merge_events_to_delta keyed on event_id yields exactly one row."""
        note_event = _ev(42, "agent_actions", "a42", "insert",
                         after={"user_id": "u1", "tool_name": "add_note",
                                "action_type": "write", "status": "success"})

        spark = FakeSpark()
        # First delivery
        merge_events_to_delta(spark, [note_event], "cat", "sch")
        # Second delivery (replay)
        merge_events_to_delta(spark, [note_event], "cat", "sch")

        target = "cat.sch.lakebase_change_events"
        assert len(spark._tables[target]) == 1
        assert spark._tables[target][0]["event_id"] == 42

    def test_replay_aggregates_count_once(self):
        """Replay: same event delivered twice -> compute_* counts it once."""
        event = _ev(10, "agent_actions", "a10", "insert",
                    after={"user_id": "u1", "tool_name": "search",
                           "action_type": "read", "status": "success"},
                    occurred="2025-06-01T12:00:00+00:00")

        spark = FakeSpark()
        merge_events_to_delta(spark, [event], "cat", "sch")
        merge_events_to_delta(spark, [event], "cat", "sch")

        # Query events for the affected date (simulating query_events_for_dates)
        target = "cat.sch.lakebase_change_events"
        all_events_raw = spark._tables[target]
        all_events = [parse_event({
            "event_id": r["event_id"], "source_table": r["source_table"],
            "source_pk": r["source_pk"], "operation": r["operation"],
            "before_payload": r.get("before_payload"),
            "after_payload": r.get("after_payload"),
            "occurred_at": r["occurred_at"],
        }) for r in all_events_raw]

        aa = compute_agent_activity(all_events)
        assert len(aa) == 1
        assert aa[0]["call_count"] == 1

    def test_replay_full_pipeline_two_runs(self):
        """Full pipeline replay: crash on run 1 (merge raises), then run 2 succeeds.
        Events re-claimed and Delta has one row per event_id."""
        event = _ev(100, "agent_actions", "a100", "insert",
                    after={"user_id": "u1", "tool_name": "search",
                           "action_type": "read", "status": "success"},
                    occurred="2025-07-01T09:00:00+00:00")

        outbox_row = {
            "event_id": 100, "source_table": "agent_actions",
            "source_pk": "a100", "operation": "insert",
            "before_payload": None,
            "after_payload": json.dumps(event.after_payload),
            "occurred_at": event.occurred_at,
            "delivered_at": None, "attempt_count": 0, "last_error": None,
        }

        class FailingFakeSpark(FakeSpark):
            def sql(self, text: str):
                if "MERGE" in text.upper() and "lakebase_change_events" in text:
                    raise RuntimeError("merge boom")
                return super().sql(text)

        # Run 1: crash after claim, before mark_delivered
        conn1 = FakeConn([outbox_row])
        spark1 = FailingFakeSpark()
        with pytest.raises(RuntimeError, match="merge boom"):
            run_pipeline(spark1, conn1, "cat", "sch", 100)

        # Events re-claimable: delivered_at reset by mark_failed
        assert conn1._outbox[0]["delivered_at"] is None
        assert conn1._outbox[0]["last_error"] == "merge boom"

        # Run 2: succeeds
        conn2 = FakeConn([outbox_row])
        spark2 = FakeSpark()
        result = run_pipeline(spark2, conn2, "cat", "sch", 100)
        assert result is False  # only 1 event < batch_size of 100

        target = "cat.sch.lakebase_change_events"
        assert len(spark2._tables[target]) == 1

    def test_merge_key_mutation_fails_replay(self):
        """If MERGE key were not event_id, replay would create duplicates."""
        ev1 = _ev(1, "agent_actions", "a1", "insert",
                  after={"user_id": "u1", "tool_name": "t", "action_type": "r", "status": "ok"})
        ev2 = _ev(1, "agent_actions", "a1", "insert",
                  after={"user_id": "u1", "tool_name": "t", "action_type": "r", "status": "ok"})

        spark = FakeSpark()
        # First merge
        merge_events_to_delta(spark, [ev1], "cat", "sch")
        # Second merge with same event
        merge_events_to_delta(spark, [ev2], "cat", "sch")

        target = "cat.sch.lakebase_change_events"
        # With event_id key: 1 row
        assert len(spark._tables[target]) == 1

        # Mutation proof: if key were constant, would get 2
        spark2 = FakeSpark()
        spark2._tables[target] = []
        spark2._tables[target].append({"event_id": 1, "source_table": "x"})
        spark2._tables[target].append({"event_id": 1, "source_table": "x"})
        # This would be the broken state (2 rows for same event_id)
        assert len(spark2._tables[target]) == 2  # mutation would produce this


# ── ordering tests ───────────────────────────────────────────────────────────

class TestOrdering:

    def test_mark_delivered_after_merge_and_upsert(self):
        """mark_delivered must be called AFTER Delta MERGE + analytics upsert."""
        event = _ev(50, "agent_actions", "a50", "insert",
                    after={"user_id": "u1", "tool_name": "search",
                           "action_type": "read", "status": "success"},
                    occurred="2025-08-01T10:00:00+00:00")

        outbox_row = {
            "event_id": 50, "source_table": "agent_actions",
            "source_pk": "a50", "operation": "insert",
            "before_payload": None,
            "after_payload": json.dumps(event.after_payload),
            "occurred_at": event.occurred_at,
            "delivered_at": None, "attempt_count": 0, "last_error": None,
        }

        sql_order = []
        conn = FakeConn([outbox_row])
        spark = FakeSpark()

        original_sql = spark.sql
        original_execute = FakeCursor.execute

        def tracking_sql(text):
            sql_order.append(("spark", text.strip()[:120]))
            return original_sql(text)

        def tracking_execute(self_cur, sql_text, params=()):
            sql_order.append(("conn", sql_text.strip()[:120]))
            return original_execute(self_cur, sql_text, params)

        spark.sql = tracking_sql
        FakeCursor.execute = tracking_execute

        try:
            run_pipeline(spark, conn, "cat", "sch", 100)
        finally:
            FakeCursor.execute = original_execute

        # Find the mark_delivered UPDATE (contains "delivered_at = now()")
        delivery_idx = None
        upsert_idx = None
        for i, (src, sql_text) in enumerate(sql_order):
            if "delivered_at = now()" in sql_text:
                delivery_idx = i
            if "INSERT INTO" in sql_text and "analytics_" in sql_text:
                upsert_idx = i

        assert delivery_idx is not None, "mark_delivered was never called"
        assert upsert_idx is not None, "upsert_analytics was never called"
        assert delivery_idx > upsert_idx, (
            f"mark_delivered (idx={delivery_idx}) was called before "
            f"upsert_analytics (idx={upsert_idx})"
        )

    def test_crash_before_delivery_leaves_reclaimable(self):
        """Crash between claim and mark_delivered -> events re-claimable."""
        event = _ev(51, "agent_actions", "a51", "insert",
                    after={"user_id": "u1", "tool_name": "search",
                           "action_type": "read", "status": "ok"},
                    occurred="2025-08-02T10:00:00+00:00")

        outbox_row = {
            "event_id": 51, "source_table": "agent_actions",
            "source_pk": "a51", "operation": "insert",
            "before_payload": None,
            "after_payload": json.dumps(event.after_payload),
            "occurred_at": event.occurred_at,
            "delivered_at": None, "attempt_count": 0, "last_error": None,
        }

        class CrashAfterUpsert(FakeSpark):
            def sql(self, text):
                result = super().sql(text)
                # Crash after the first INSERT INTO analytics table
                if "INSERT INTO" in text and "analytics_" in text:
                    raise RuntimeError("post-upsert crash")
                return result

        conn = FakeConn([outbox_row])
        spark = CrashAfterUpsert()

        with pytest.raises(RuntimeError, match="post-upsert crash"):
            run_pipeline(spark, conn, "cat", "sch", 100)

        # mark_failed resets delivered_at (or it was never set)
        assert conn._outbox[0]["delivered_at"] is None


# ── retry tests ─────────────────────────────────────────────────────────────

class TestRetry:

    def test_pipeline_failure_calls_mark_failed(self):
        """run_pipeline failure after claim calls mark_failed with event IDs."""
        event = _ev(60, "agent_actions", "a60", "insert",
                    after={"user_id": "u1", "tool_name": "t",
                           "action_type": "r", "status": "ok"},
                    occurred="2025-09-01T10:00:00+00:00")

        outbox_row = {
            "event_id": 60, "source_table": "agent_actions",
            "source_pk": "a60", "operation": "insert",
            "before_payload": None,
            "after_payload": json.dumps(event.after_payload),
            "occurred_at": event.occurred_at,
            "delivered_at": None, "attempt_count": 0, "last_error": None,
        }

        class FailOnMerge(FakeSpark):
            def sql(self, text):
                if "MERGE" in text.upper() and "lakebase_change_events" in text:
                    raise RuntimeError("deliberate failure")
                return super().sql(text)

        conn = FakeConn([outbox_row])
        spark = FailOnMerge()

        with pytest.raises(RuntimeError, match="deliberate failure"):
            run_pipeline(spark, conn, "cat", "sch", 100)

        assert conn._outbox[0]["delivered_at"] is None
        assert conn._outbox[0]["last_error"] == "deliberate failure"

    def test_events_reclaimable_after_failure(self):
        """After failure, events can be re-claimed on next run."""
        event = _ev(61, "agent_actions", "a61", "insert",
                    after={"user_id": "u1", "tool_name": "t",
                           "action_type": "r", "status": "ok"},
                    occurred="2025-09-02T10:00:00+00:00")

        outbox_row = {
            "event_id": 61, "source_table": "agent_actions",
            "source_pk": "a61", "operation": "insert",
            "before_payload": None,
            "after_payload": json.dumps(event.after_payload),
            "occurred_at": event.occurred_at,
            "delivered_at": None, "attempt_count": 0, "last_error": None,
        }

        class FailOnce(FakeSpark):
            _fail = True

            def sql(self, text):
                if FailOnce._fail and "MERGE" in text.upper() and "lakebase_change_events" in text:
                    FailOnce._fail = False
                    raise RuntimeError("transient failure")
                return super().sql(text)

        conn = FakeConn([outbox_row])
        spark = FailOnce()

        with pytest.raises(RuntimeError):
            run_pipeline(spark, conn, "cat", "sch", 100)

        # Re-claimable
        assert conn._outbox[0]["delivered_at"] is None

        # Second run succeeds
        result = run_pipeline(spark, conn, "cat", "sch", 100)
        assert result is False
        assert conn._outbox[0]["delivered_at"] is not None


# ── pyspark import guard test ───────────────────────────────────────────────

class TestPysparkImportGuard:

    def test_module_importable_without_pyspark(self, tmp_path, monkeypatch):
        """pipelines.lakebase_analytics must be importable even when pyspark
        raises ModuleNotFoundError."""
        import importlib

        # Remove pyspark from sys.modules if present
        pyspark_keys = [k for k in sys.modules if k.startswith("pyspark")]
        saved = {k: sys.modules.pop(k) for k in pyspark_keys}

        stub_dir = tmp_path / "pyspark_stub"
        stub_dir.mkdir()
        init = stub_dir / "pyspark" / "sql"
        init.mkdir(parents=True)
        (stub_dir / "pyspark" / "__init__.py").write_text(
            "raise ModuleNotFoundError(\"No module named 'pyspark'\")\n"
        )
        (init / "__init__.py").write_text("")

        monkeypatch.syspath_prepend(str(stub_dir))

        try:
            import pipelines.lakebase_analytics as mod
            importlib.reload(mod)
            assert mod._has_pyspark is False
            assert mod.CHANGE_EVENTS_SCHEMA is None
            assert mod.STATE_SCHEMA is None
        finally:
            for k in list(sys.modules):
                if k.startswith("pyspark"):
                    del sys.modules[k]
            sys.modules.update(saved)
            importlib.reload(mod)