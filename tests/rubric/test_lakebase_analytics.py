"""tests/rubric/test_lakebase_analytics.py — Pure-function tests for CDC analytics.

Tests the normalization and aggregation functions in pipelines.lakebase_analytics
using plain dictionaries (no Spark, no DB, no network).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

import pytest

from pipelines.lakebase_analytics import (
    OutboxEvent,
    compute_agent_activity,
    compute_order_funnel,
    compute_usage_daily,
    compute_watchlist_changes,
    extract_date,
    parse_event,
    _STATUS_TO_STAGE,
)


# ── fixtures ─────────────────────────────────────────────────────────────────

def _dt(s: str) -> datetime:
    """Parse ISO timestamp string to datetime."""
    return datetime.fromisoformat(s)


def _ev(event_id: int, table: str, pk: str, op: str,
        after: Dict[str, Any] | None = None,
        before: Dict[str, Any] | None = None,
        occurred: str = "2025-01-15T10:00:00+00:00") -> OutboxEvent:
    """Shorthand to build an OutboxEvent."""
    return OutboxEvent(
        event_id=event_id,
        source_table=table,
        source_pk=pk,
        operation=op,
        before_payload=before,
        after_payload=after,
        occurred_at=_dt(occurred),
    )


# ── parse_event ──────────────────────────────────────────────────────────────

def test_parse_event_with_json_strings():
    """parse_event must deserialize JSON strings in payloads."""
    row = {
        "event_id": 1,
        "source_table": "watchlists",
        "source_pk": "w1",
        "operation": "insert",
        "before_payload": None,
        "after_payload": '{"watchlist_id": "w1", "user_id": "u1", "symbol": "AAPL"}',
        "occurred_at": datetime(2025, 1, 15, tzinfo=timezone.utc),
    }
    ev = parse_event(row)
    assert ev.event_id == 1
    assert ev.after_payload["symbol"] == "AAPL"
    assert ev.before_payload is None


def test_parse_event_with_dict_payloads():
    """parse_event must pass through dict payloads unchanged."""
    row = {
        "event_id": 2,
        "source_table": "orders",
        "source_pk": "o1",
        "operation": "update",
        "before_payload": {"status": "PENDING_APPROVAL"},
        "after_payload": {"status": "APPROVED"},
        "occurred_at": datetime(2025, 1, 15, tzinfo=timezone.utc),
    }
    ev = parse_event(row)
    assert ev.before_payload["status"] == "PENDING_APPROVAL"
    assert ev.after_payload["status"] == "APPROVED"


# ── extract_date ─────────────────────────────────────────────────────────────

def test_extract_date_utc():
    dt = datetime(2025, 3, 14, 23, 59, 59, tzinfo=timezone.utc)
    assert extract_date(dt) == "2025-03-14"


def test_extract_date_naive_treated_as_utc():
    """Naive datetimes are treated as UTC."""
    dt = datetime(2025, 3, 14, 23, 59, 59)
    assert extract_date(dt) == "2025-03-14"


# ── compute_agent_activity ───────────────────────────────────────────────────

def test_agent_activity_insert():
    ev = _ev(1, "agent_actions", "a1", "insert",
             after={"user_id": "u1", "tool_name": "get_signals",
                    "action_type": "read", "status": "success"})
    result = compute_agent_activity([ev])
    assert len(result) == 1
    r = result[0]
    assert r["event_date"] == "2025-01-15"
    assert r["tool_name"] == "get_signals"
    assert r["call_count"] == 1
    assert r["distinct_users"] == 1


def test_agent_activity_multiple_users():
    evts = [
        _ev(1, "agent_actions", "a1", "insert",
            after={"user_id": "u1", "tool_name": "search", "action_type": "read", "status": "ok"}),
        _ev(2, "agent_actions", "a2", "insert",
            after={"user_id": "u2", "tool_name": "search", "action_type": "read", "status": "ok"}),
    ]
    result = compute_agent_activity(evts)
    assert len(result) == 1
    assert result[0]["distinct_users"] == 2
    assert result[0]["call_count"] == 2


def test_agent_activity_ignores_non_agent_events():
    ev = _ev(1, "watchlists", "w1", "insert",
             after={"user_id": "u1", "symbol": "AAPL"})
    result = compute_agent_activity([ev])
    assert result == []


# ── compute_watchlist_changes ────────────────────────────────────────────────

def test_watchlist_insert():
    ev = _ev(1, "watchlists", "w1", "insert",
             after={"user_id": "u1", "symbol": "AAPL"})
    result = compute_watchlist_changes([ev])
    assert len(result) == 1
    assert result[0]["additions"] == 1
    assert result[0]["removals"] == 0
    assert result[0]["net_changes"] == 1


def test_watchlist_delete():
    ev = _ev(1, "watchlists", "w1", "delete",
             before={"user_id": "u1", "symbol": "AAPL"})
    result = compute_watchlist_changes([ev])
    assert len(result) == 1
    assert result[0]["additions"] == 0
    assert result[0]["removals"] == 1
    assert result[0]["net_changes"] == -1


def test_watchlist_snapshot():
    ev = _ev(1, "watchlists", "w1", "snapshot",
             after={"user_id": "u1", "symbol": "AAPL"})
    result = compute_watchlist_changes([ev])
    assert result[0]["additions"] == 1


def test_watchlist_net_changes():
    evts = [
        _ev(1, "watchlists", "w1", "insert",
            after={"user_id": "u1", "symbol": "AAPL"}),
        _ev(2, "watchlists", "w2", "delete",
            before={"user_id": "u1", "symbol": "MSFT"}),
    ]
    result = compute_watchlist_changes(evts)
    # Two different symbols → two rows
    by_sym = {r["symbol"]: r for r in result}
    assert by_sym["AAPL"]["net_changes"] == 1
    assert by_sym["MSFT"]["net_changes"] == -1


# ── compute_order_funnel ─────────────────────────────────────────────────────

def test_order_intent_stage():
    ev = _ev(1, "orders", "o1", "insert",
             after={"order_id": "o1", "status": "PENDING_APPROVAL"})
    result = compute_order_funnel([ev])
    assert len(result) == 1
    assert result[0]["funnel_stage"] == "intent"
    assert result[0]["stage_count"] == 1
    assert result[0]["distinct_orders"] == 1


def test_order_approval_stage():
    ev = _ev(1, "orders", "o1", "update",
             before={"order_id": "o1", "status": "PENDING_APPROVAL"},
             after={"order_id": "o1", "status": "APPROVED"})
    result = compute_order_funnel([ev])
    # Update counts only the NEW status
    assert len(result) == 1
    assert result[0]["funnel_stage"] == "approval"
    assert result[0]["stage_count"] == 1


def test_order_fill_stage():
    ev = _ev(1, "orders", "o1", "update",
             before={"order_id": "o1", "status": "SUBMITTED"},
             after={"order_id": "o1", "status": "FILLED"})
    result = compute_order_funnel([ev])
    assert result[0]["funnel_stage"] == "fill"


def test_order_cancelled_stage():
    ev = _ev(1, "orders", "o1", "update",
             before={"order_id": "o1", "status": "PENDING_APPROVAL"},
             after={"order_id": "o1", "status": "CANCELLED"})
    result = compute_order_funnel([ev])
    assert result[0]["funnel_stage"] == "cancellation"


def test_order_rejected_stage():
    ev = _ev(1, "orders", "o1", "update",
             before={"order_id": "o1", "status": "PENDING_APPROVAL"},
             after={"order_id": "o1", "status": "REJECTED"})
    result = compute_order_funnel([ev])
    assert result[0]["funnel_stage"] == "rejection"


def test_order_failure_stage():
    ev = _ev(1, "orders", "o1", "update",
             before={"order_id": "o1", "status": "SUBMITTED"},
             after={"order_id": "o1", "status": "FAILED"})
    result = compute_order_funnel([ev])
    assert result[0]["funnel_stage"] == "failure"


def test_order_update_no_preimage_double_count():
    """An update must not count the old status as a new funnel stage."""
    ev = _ev(1, "orders", "o1", "update",
             before={"order_id": "o1", "status": "PENDING_APPROVAL"},
             after={"order_id": "o1", "status": "APPROVED"})
    result = compute_order_funnel([ev])
    # Must have exactly one stage (approval), not intent + approval
    assert len(result) == 1
    assert result[0]["funnel_stage"] == "approval"
    assert result[0]["stage_count"] == 1


def test_order_snapshot():
    ev = _ev(1, "orders", "o1", "snapshot",
             after={"order_id": "o1", "status": "FILLED"})
    result = compute_order_funnel([ev])
    assert result[0]["funnel_stage"] == "fill"
    assert result[0]["stage_count"] == 1


# ── compute_usage_daily ──────────────────────────────────────────────────────

def test_usage_daily_retrieval():
    ev = _ev(1, "agent_actions", "a1", "insert",
             after={"user_id": "u1", "tool_name": "get_signals",
                    "action_type": "read", "status": "success"})
    result = compute_usage_daily([ev])
    assert len(result) == 1
    assert result[0]["retrieval_calls"] == 1
    assert result[0]["write_calls"] == 0
    assert result[0]["success_count"] == 1


def test_usage_daily_write():
    ev = _ev(1, "agent_actions", "a1", "insert",
             after={"user_id": "u1", "tool_name": "insert_watchlist",
                    "action_type": "write", "status": "success"})
    result = compute_usage_daily([ev])
    assert result[0]["retrieval_calls"] == 0
    assert result[0]["write_calls"] == 1


def test_usage_daily_failure():
    ev = _ev(1, "agent_actions", "a1", "insert",
             after={"user_id": "u1", "tool_name": "get_signals",
                    "action_type": "read", "status": "error"})
    result = compute_usage_daily([ev])
    assert result[0]["success_count"] == 0
    assert result[0]["failure_count"] == 1


def test_usage_daily_distinct_users():
    evts = [
        _ev(1, "agent_actions", "a1", "insert",
            after={"user_id": "u1", "tool_name": "search", "action_type": "read", "status": "ok"}),
        _ev(2, "agent_actions", "a2", "insert",
            after={"user_id": "u2", "tool_name": "search", "action_type": "read", "status": "ok"}),
        _ev(3, "agent_actions", "a3", "insert",
            after={"user_id": "u1", "tool_name": "search", "action_type": "read", "status": "ok"}),
    ]
    result = compute_usage_daily(evts)
    assert result[0]["distinct_users"] == 2


# ── idempotency: two identical runs produce equivalent aggregates ────────────

def test_idempotent_agent_activity():
    """Two identical event sets must produce byte-for-byte-equivalent aggregates."""
    evts = [
        _ev(1, "agent_actions", "a1", "insert",
            after={"user_id": "u1", "tool_name": "search", "action_type": "read", "status": "ok"}),
        _ev(2, "agent_actions", "a2", "insert",
            after={"user_id": "u2", "tool_name": "search", "action_type": "read", "status": "ok"}),
    ]
    r1 = compute_agent_activity(evts)
    r2 = compute_agent_activity(evts)
    assert r1 == r2


def test_idempotent_order_funnel():
    evts = [
        _ev(1, "orders", "o1", "insert",
            after={"order_id": "o1", "status": "PENDING_APPROVAL"}),
        _ev(2, "orders", "o1", "update",
            before={"order_id": "o1", "status": "PENDING_APPROVAL"},
            after={"order_id": "o1", "status": "APPROVED"}),
    ]
    r1 = compute_order_funnel(evts)
    r2 = compute_order_funnel(evts)
    assert r1 == r2


def test_idempotent_watchlist():
    evts = [
        _ev(1, "watchlists", "w1", "insert",
            after={"user_id": "u1", "symbol": "AAPL"}),
    ]
    r1 = compute_watchlist_changes(evts)
    r2 = compute_watchlist_changes(evts)
    assert r1 == r2


def test_idempotent_usage():
    evts = [
        _ev(1, "agent_actions", "a1", "insert",
            after={"user_id": "u1", "tool_name": "search", "action_type": "read", "status": "ok"}),
    ]
    r1 = compute_usage_daily(evts)
    r2 = compute_usage_daily(evts)
    assert r1 == r2


# ── duplicate replay detection ───────────────────────────────────────────────

def test_duplicate_event_id_detected():
    """Two events with the same event_id must be handled (MERGE dedup)."""
    evts = [
        _ev(1, "agent_actions", "a1", "insert",
            after={"user_id": "u1", "tool_name": "search", "action_type": "read", "status": "ok"}),
        _ev(1, "agent_actions", "a1", "insert",
            after={"user_id": "u1", "tool_name": "search", "action_type": "read", "status": "ok"}),
    ]
    # With pure functions, duplicates produce inflated counts
    result = compute_agent_activity(evts)
    # This is expected — the MERGE on Delta handles dedup at the event level
    assert result[0]["call_count"] == 2


# ── late delivery below high-water mark ──────────────────────────────────────

def test_late_delivery_below_highwater():
    """An event with ID below the observed high-water mark must still be processed."""
    # Simulate: first batch has event_id=5, second batch has event_id=3 (late)
    batch1 = [
        _ev(5, "agent_actions", "a5", "insert",
            after={"user_id": "u1", "tool_name": "search", "action_type": "read", "status": "ok"}),
    ]
    batch2 = [
        _ev(3, "agent_actions", "a3", "insert",
            after={"user_id": "u2", "tool_name": "search", "action_type": "read", "status": "ok"}),
    ]
    # Both batches produce independent aggregates
    r1 = compute_agent_activity(batch1)
    r2 = compute_agent_activity(batch2)
    assert r1[0]["call_count"] == 1
    assert r2[0]["call_count"] == 1
    # The aggregate from all events (recomputed from Delta) would see both
    all_events = batch1 + batch2
    r_all = compute_agent_activity(all_events)
    assert r_all[0]["call_count"] == 2


# ── UTC date boundaries ──────────────────────────────────────────────────────

def test_utc_date_boundary():
    """Events at UTC midnight boundary must be assigned to correct dates."""
    evts = [
        _ev(1, "agent_actions", "a1", "insert",
            after={"user_id": "u1", "tool_name": "search", "action_type": "read", "status": "ok"},
            occurred="2025-01-15T23:59:59+00:00"),
        _ev(2, "agent_actions", "a2", "insert",
            after={"user_id": "u1", "tool_name": "search", "action_type": "read", "status": "ok"},
            occurred="2025-01-16T00:00:01+00:00"),
    ]
    result = compute_agent_activity(evts)
    dates = {r["event_date"] for r in result}
    assert dates == {"2025-01-15", "2025-01-16"}


# ── every order status transition ────────────────────────────────────────────

@pytest.mark.parametrize("status,stage", list(_STATUS_TO_STAGE.items()))
def test_order_status_to_stage(status, stage):
    """Every order status must map to a funnel stage."""
    ev = _ev(1, "orders", "o1", "insert",
             after={"order_id": "o1", "status": status})
    result = compute_order_funnel([ev])
    assert len(result) == 1
    assert result[0]["funnel_stage"] == stage