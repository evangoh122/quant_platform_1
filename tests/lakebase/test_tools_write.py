"""Write-tool round-trip tests — require live Lakebase (`-m lakebase`).

Each tool writes transactionally, then the test reads the row back and asserts
it. The approve/cancel paths are exercised through the public tool signatures
(no injected risk engine, market session, or bridge — the production entry
points acquire those themselves). Determinism is achieved by monkeypatching the
clock and the bridge *construction site*, never by passing trusted state in.
"""
import uuid
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.lakebase

import agent.tools_write as tw
from agent.tools_retrieval import get_open_orders, get_watchlist


def _seed_account(db, account_id, buying_power=100000.0):
    with db.transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO accounts (account_id, buying_power) VALUES (%s, %s) "
                "ON CONFLICT (account_id) DO NOTHING",
                (account_id, buying_power),
            )


def _cleanup_account(db, account_id):
    with db.transaction() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM accounts WHERE account_id = %s", (account_id,))


def _seed_user(db, user_id, role="trader"):
    with db.transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (user_id, display_name, role) VALUES (%s, %s, %s) "
                "ON CONFLICT (user_id) DO NOTHING",
                (user_id, user_id, role),
            )


def _allowlisted_symbol():
    from config.tickers import get_all_ticker_symbols

    symbols = get_all_ticker_symbols()
    assert symbols, "tickers.yaml must contain at least one symbol"
    return symbols[0]


def _place_order(db, uid, monkeypatch, *, broker_order_id="PAPER-42"):
    """Create + approve + place an order through the public tool signatures."""
    symbol = _allowlisted_symbol()
    _seed_account(db, uid)
    # Approval authority is out-of-band; the owner must be a vetted 'trader'.
    _seed_user(db, uid, role="trader")
    order = tw.create_order_intent(symbol, "BUY", 10, notional=1000.0,
                                   user_id=uid, db=db)
    tw.record_approval(order["order_id"], tw.ApprovalContext(approver_id=uid), db=db)

    monkeypatch.setattr(tw, "is_market_session_open", lambda: True)
    monkeypatch.setattr(tw, "get_lakebase", lambda: db)
    mock_bridge = MagicMock()
    mock_bridge.submit_order.return_value = {
        "status": "SUBMITTED", "broker_order_id": broker_order_id,
    }
    mock_bridge.cancel_order.return_value = {
        "status": "CANCELLED", "broker_order_id": broker_order_id,
    }
    monkeypatch.setattr(tw, "IBKRBridge", lambda: mock_bridge)

    res = tw.approve_and_place_paper_order(order["order_id"])
    assert res["ok"] is True
    return order, mock_bridge


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


def test_duplicate_idempotency_key_replay_no_broker_call(migrated, cleanup_user, monkeypatch):
    uid = cleanup_user()
    try:
        symbol = _allowlisted_symbol()
        _seed_account(migrated, uid)
        _seed_user(migrated, uid, role="trader")
        key = f"dup-{uuid.uuid4()}"
        r1 = tw.create_order_intent(symbol, "BUY", 10, notional=1000.0,
                                    idempotency_key=key, user_id=uid, db=migrated)
        assert r1["status"] == "PENDING_APPROVAL"

        # Replay the same key: structured duplicate reason, same order, no new row.
        r2 = tw.create_order_intent(symbol, "BUY", 10, notional=1000.0,
                                    idempotency_key=key, user_id=uid, db=migrated)
        assert r2["order_id"] == r1["order_id"]
        assert r2["reason"] == "DUPLICATE_IDEMPOTENCY_KEY"
        assert r2["replay"] is True

        # Place through the public path (patching broker construction, not state).
        tw.record_approval(r1["order_id"], tw.ApprovalContext(approver_id=uid), db=migrated)
        monkeypatch.setattr(tw, "is_market_session_open", lambda: True)
        monkeypatch.setattr(tw, "get_lakebase", lambda: migrated)
        mock_bridge = MagicMock()
        mock_bridge.submit_order.return_value = {
            "status": "SUBMITTED", "broker_order_id": "PAPER-42",
        }
        monkeypatch.setattr(tw, "IBKRBridge", lambda: mock_bridge)

        res = tw.approve_and_place_paper_order(r1["order_id"])
        assert res["ok"] is True
        mock_bridge.submit_order.assert_called_once()

        # Re-placing the same (deduplicated) order id is a replay: no second call.
        res2 = tw.approve_and_place_paper_order(r2["order_id"])
        assert res2.get("replay") is True
        mock_bridge.submit_order.assert_called_once()
    finally:
        _cleanup_account(migrated, uid)


def test_record_agent_action_roundtrip(migrated, cleanup_user):
    uid = cleanup_user()
    res = tw.record_agent_action("t", "write", "i", "o", user_id=uid, db=migrated)
    row = migrated.fetchone(
        "SELECT tool_name FROM agent_actions WHERE action_id = %s", (res["action_id"],)
    )
    assert row[0] == "t"


def test_get_open_orders_reads_lakebase(migrated, cleanup_user):
    uid = cleanup_user()
    tw.create_order_intent("TEST", "BUY", 10, notional=1000.0, user_id=uid, db=migrated)
    open_orders = get_open_orders(user_id=uid, db=migrated)
    assert any(o["symbol"] == "TEST" for o in open_orders)


def test_record_approval_roundtrip(migrated, cleanup_user):
    uid = cleanup_user()
    _seed_user(migrated, uid, role="trader")
    order = tw.create_order_intent("TEST", "BUY", 10, notional=1000.0,
                                   user_id=uid, db=migrated)
    res = tw.record_approval(order["order_id"], tw.ApprovalContext(approver_id=uid), db=migrated)
    assert res["status"] == "APPROVED"
    row = migrated.fetchone(
        "SELECT status, approved_by FROM orders WHERE order_id = %s",
        (order["order_id"],),
    )
    assert row == ("APPROVED", uid)
    arow = migrated.fetchone(
        "SELECT approver_id FROM approvals WHERE order_id = %s",
        (order["order_id"],),
    )
    assert arow == (uid,)


def test_record_approval_rejects_unknown_approver(migrated, cleanup_user, monkeypatch):
    uid = cleanup_user()
    order = tw.create_order_intent("TEST", "BUY", 10, notional=1000.0,
                                   user_id=uid, db=migrated)
    unknown = f"nobody_{uuid.uuid4().hex}"
    res = tw.record_approval(order["order_id"],
                             tw.ApprovalContext(approver_id=unknown), db=migrated)
    assert res["ok"] is False
    assert res["reason"] == "UNKNOWN_APPROVER"

    # No approval row was written, so placement is rejected without a broker call.
    monkeypatch.setattr(tw, "is_market_session_open", lambda: True)
    monkeypatch.setattr(tw, "get_lakebase", lambda: migrated)
    mock_bridge = MagicMock()
    mock_bridge.submit_order.return_value = {
        "status": "SUBMITTED", "broker_order_id": "PAPER-1",
    }
    monkeypatch.setattr(tw, "IBKRBridge", lambda: mock_bridge)
    res2 = tw.approve_and_place_paper_order(order["order_id"])
    assert res2["ok"] is False
    mock_bridge.submit_order.assert_not_called()


def test_record_approval_rejects_non_approver_role(migrated, cleanup_user):
    uid = cleanup_user()
    approver = cleanup_user()
    _seed_user(migrated, approver, role="observer")
    order = tw.create_order_intent("TEST", "BUY", 10, notional=1000.0,
                                   user_id=uid, db=migrated)
    res = tw.record_approval(order["order_id"],
                             tw.ApprovalContext(approver_id=approver), db=migrated)
    assert res["ok"] is False
    assert res["reason"] == "APPROVER_NOT_PERMITTED"
    assert res["detail"]["role"] == "observer"


def test_auto_provisioned_id_cannot_approve(migrated, cleanup_user, monkeypatch):
    """Round-5 exploit regression: touching a write tool with a fabricated id
    must not mint an approver. The id is auto-provisioned as 'viewer', so
    record_approval rejects it with APPROVER_NOT_PERMITTED and placement is
    rejected with no broker call."""
    uid = cleanup_user()
    fake = cleanup_user()
    order = tw.create_order_intent("TEST", "BUY", 10, notional=1000.0,
                                   user_id=uid, db=migrated)
    # The bypass attempt: auto-provision the fabricated id via another tool.
    tw.add_to_watchlist("MSFT", user_id=fake, db=migrated)
    res = tw.record_approval(order["order_id"],
                             tw.ApprovalContext(approver_id=fake), db=migrated)
    assert res["ok"] is False
    assert res["reason"] == "APPROVER_NOT_PERMITTED"

    monkeypatch.setattr(tw, "is_market_session_open", lambda: True)
    monkeypatch.setattr(tw, "get_lakebase", lambda: migrated)
    mock_bridge = MagicMock()
    mock_bridge.submit_order.return_value = {
        "status": "SUBMITTED", "broker_order_id": "PAPER-1",
    }
    monkeypatch.setattr(tw, "IBKRBridge", lambda: mock_bridge)
    res2 = tw.approve_and_place_paper_order(order["order_id"])
    assert res2["ok"] is False
    mock_bridge.submit_order.assert_not_called()


def test_granted_approver_cannot_approve_other_users_order(migrated, cleanup_user, monkeypatch):
    """A vetted 'trader' approver may not approve another user's order: it is a
    single-user paper-trading tool, so 'explicit human approval' means a user
    confirming their own order."""
    uid = cleanup_user()
    approver = cleanup_user()
    _seed_user(migrated, approver, role="trader")
    order = tw.create_order_intent("TEST", "BUY", 10, notional=1000.0,
                                   user_id=uid, db=migrated)
    res = tw.record_approval(order["order_id"],
                             tw.ApprovalContext(approver_id=approver), db=migrated)
    assert res["ok"] is False
    assert res["reason"] == "APPROVER_NOT_OWNER"
    assert res["detail"]["owner_id"] == uid

    monkeypatch.setattr(tw, "is_market_session_open", lambda: True)
    monkeypatch.setattr(tw, "get_lakebase", lambda: migrated)
    mock_bridge = MagicMock()
    mock_bridge.submit_order.return_value = {
        "status": "SUBMITTED", "broker_order_id": "PAPER-1",
    }
    monkeypatch.setattr(tw, "IBKRBridge", lambda: mock_bridge)
    res2 = tw.approve_and_place_paper_order(order["order_id"])
    assert res2["ok"] is False
    mock_bridge.submit_order.assert_not_called()


def test_approve_places_via_public_signature(migrated, cleanup_user, monkeypatch):
    uid = cleanup_user()
    try:
        order, mock_bridge = _place_order(migrated, uid, monkeypatch)
        mock_bridge.submit_order.assert_called_once()
        row = migrated.fetchone(
            "SELECT status, broker_order_id, approved_by FROM orders WHERE order_id = %s",
            (order["order_id"],),
        )
        assert row == ("SUBMITTED", "PAPER-42", uid)
    finally:
        _cleanup_account(migrated, uid)


def test_cancel_paper_order_roundtrip(migrated, cleanup_user, monkeypatch):
    uid = cleanup_user()
    try:
        order, mock_bridge = _place_order(migrated, uid, monkeypatch)
        res = tw.cancel_paper_order(order["order_id"], user_id=uid, db=migrated)
        assert res["status"] == "CANCELLED"
        assert res["ok"] is True
        mock_bridge.cancel_order.assert_called_once_with("PAPER-42")
        row = migrated.fetchone(
            "SELECT status FROM orders WHERE order_id = %s", (order["order_id"],)
        )
        assert row == ("CANCELLED",)
    finally:
        _cleanup_account(migrated, uid)


def test_cancel_paper_order_bridge_failure(migrated, cleanup_user, monkeypatch):
    uid = cleanup_user()
    try:
        order, mock_bridge = _place_order(migrated, uid, monkeypatch)
        mock_bridge.cancel_order.return_value = {"status": "REJECTED", "broker_order_id": "PAPER-42"}
        res = tw.cancel_paper_order(order["order_id"], user_id=uid, db=migrated)
        assert res["ok"] is False
        assert res["status"] == "FAILED"
        row = migrated.fetchone(
            "SELECT status FROM orders WHERE order_id = %s", (order["order_id"],)
        )
        assert row == ("FAILED",)
    finally:
        _cleanup_account(migrated, uid)
