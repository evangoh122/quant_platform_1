"""Write-tool round-trip tests — require live Lakebase (`-m lakebase`).

Each tool writes transactionally, then the test reads the row back and asserts
it. Risk-failure paths assert the bridge is never called.
"""
import uuid
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.lakebase

import agent.tools_write as tw
from agent.guardrails import RiskEngine
from agent.tools_retrieval import get_open_orders, get_watchlist


def test_add_to_watchlist_roundtrip_and_idempotent(migrated, cleanup_user):
    uid = cleanup_user()
    res = tw.add_to_watchlist("TEST", user_id=uid, db=migrated)
    assert res["symbol"] == "TEST"

    wl = get_watchlist(user_id=uid, db=migrated)
    assert any(w["symbol"] == "TEST" for w in wl)

    res2 = tw.add_to_watchlist("TEST", user_id=uid, db=migrated)
    assert res2["watchlist_id"] == res["watchlist_id"]


def test_save_research_note_roundtrip(migrated, cleanup_user):
    uid = cleanup_user()
    res = tw.save_research_note("TEST", "note text here", user_id=uid, db=migrated)
    row = migrated.fetchone(
        "SELECT note_text, symbol FROM research_notes WHERE note_id = %s",
        (res["note_id"],),
    )
    assert row == ("note text here", "TEST")


def test_create_order_intent_roundtrip(migrated, cleanup_user):
    uid = cleanup_user()
    res = tw.create_order_intent(
        "TEST", "BUY", 10, notional=1000.0,
        idempotency_key=f"key-{uuid.uuid4()}", user_id=uid, db=migrated,
    )
    assert res["status"] == "PENDING_APPROVAL"
    row = migrated.fetchone(
        "SELECT status, symbol, side FROM orders WHERE order_id = %s",
        (res["order_id"],),
    )
    assert row == ("PENDING_APPROVAL", "TEST", "BUY")


def test_create_order_intent_idempotent(migrated, cleanup_user):
    uid = cleanup_user()
    key = f"idem-{uuid.uuid4()}"
    r1 = tw.create_order_intent("TEST", "BUY", 10, notional=1000.0,
                                idempotency_key=key, user_id=uid, db=migrated)
    r2 = tw.create_order_intent("TEST", "BUY", 10, notional=1000.0,
                                idempotency_key=key, user_id=uid, db=migrated)
    assert r1["order_id"] == r2["order_id"]
    cnt = migrated.fetchone(
        "SELECT count(*) FROM orders WHERE idempotency_key = %s", (key,)
    )
    assert cnt[0] == 1


def test_record_agent_action_roundtrip(migrated, cleanup_user):
    uid = cleanup_user()
    res = tw.record_agent_action("t", "write", "i", "o", user_id=uid, db=migrated)
    row = migrated.fetchone(
        "SELECT tool_name FROM agent_actions WHERE action_id = %s", (res["action_id"],)
    )
    assert row[0] == "t"


def test_approve_no_broker_call_when_risk_fails(migrated, cleanup_user):
    uid = cleanup_user()
    bridge = MagicMock()
    order = tw.create_order_intent("TEST", "BUY", 10, notional=1000.0,
                                   user_id=uid, db=migrated)
    engine = RiskEngine(allowed_symbols=set())  # symbol fails the allow-list
    res = tw.approve_and_place_paper_order(
        order["order_id"], "alice", human_approved=True,
        db=migrated, bridge=bridge, engine=engine, market_session_open=True,
    )
    assert res["ok"] is False
    assert res["status"] == "REJECTED"
    bridge.submit_order.assert_not_called()


def test_approve_requires_human_approval(migrated, cleanup_user):
    uid = cleanup_user()
    bridge = MagicMock()
    order = tw.create_order_intent("TEST", "BUY", 10, notional=1000.0,
                                   user_id=uid, db=migrated)
    engine = RiskEngine(allowed_symbols={"TEST"})
    res = tw.approve_and_place_paper_order(
        order["order_id"], "alice", human_approved=False,
        db=migrated, bridge=bridge, engine=engine, market_session_open=True,
    )
    assert res["ok"] is False
    assert res["status"] == "REJECTED"
    bridge.submit_order.assert_not_called()


def test_approve_calls_bridge_when_approved(migrated, cleanup_user):
    uid = cleanup_user()
    bridge = MagicMock()
    bridge.submit_order.return_value = {"status": "SUBMITTED", "broker_order_id": "PAPER-42"}
    order = tw.create_order_intent("TEST", "BUY", 10, notional=1000.0,
                                   user_id=uid, db=migrated)
    engine = RiskEngine(allowed_symbols={"TEST"})
    res = tw.approve_and_place_paper_order(
        order["order_id"], "alice", human_approved=True,
        db=migrated, bridge=bridge, engine=engine, market_session_open=True,
    )
    assert res["ok"] is True
    assert res["status"] == "SUBMITTED"
    assert res["broker_order_id"] == "PAPER-42"
    bridge.submit_order.assert_called_once()
    row = migrated.fetchone(
        "SELECT status, broker_order_id, approved_by FROM orders WHERE order_id = %s",
        (order["order_id"],),
    )
    assert row == ("SUBMITTED", "PAPER-42", "alice")


def test_get_open_orders_reads_lakebase(migrated, cleanup_user):
    uid = cleanup_user()
    tw.create_order_intent("TEST", "BUY", 10, notional=1000.0, user_id=uid, db=migrated)
    open_orders = get_open_orders(user_id=uid, db=migrated)
    assert any(o["symbol"] == "TEST" for o in open_orders)


def test_cancel_paper_order(migrated, cleanup_user):
    uid = cleanup_user()
    bridge = MagicMock()
    bridge.submit_order.return_value = {"status": "SUBMITTED", "broker_order_id": "PAPER-7"}
    order = tw.create_order_intent("TEST", "BUY", 10, notional=1000.0,
                                   user_id=uid, db=migrated)
    engine = RiskEngine(allowed_symbols={"TEST"})
    tw.approve_and_place_paper_order(
        order["order_id"], "alice", human_approved=True,
        db=migrated, bridge=bridge, engine=engine, market_session_open=True,
    )
    res = tw.cancel_paper_order(order["order_id"], user_id=uid, db=migrated, bridge=bridge)
    assert res["status"] == "CANCELLED"
    bridge.cancel_order.assert_called_once_with("PAPER-7")
