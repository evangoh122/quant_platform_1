"""Role-based authorization: viewer cannot approve; approver can."""

from __future__ import annotations


def test_new_viewer_cannot_approve_order(client, fake_lakebase):
    resp = client.post(
        "/api/orders/ord_123/approve",
        headers={"x-forwarded-email": "viewer@example.com"},
    )
    assert resp.status_code == 403
    assert fake_lakebase.roles["viewer@example.com"] == "viewer"


def test_approver_without_role_cannot_approve(client, fake_lakebase):
    # A trader (not an approver) is still forbidden from approving.
    fake_lakebase.roles["trader@example.com"] = "trader"
    resp = client.post(
        "/api/orders/ord_123/approve",
        headers={"x-forwarded-email": "trader@example.com"},
    )
    assert resp.status_code == 403


def test_approver_reaches_approval_path(client, fake_lakebase, monkeypatch):
    # An approver passes the role gate; the downstream write tools are
    # monkeypatched so we can assert the *authenticated* principal is threaded
    # in as the approver (never read from body/query/header).
    import agent.tools_write as tools_write

    captured = {}

    class FakeApprovalContext:
        def __init__(self, approver_id):
            self.approver_id = approver_id

    def fake_record_approval(order_id, approver):
        captured["order_id"] = order_id
        captured["approver_id"] = approver.approver_id
        return {"order_id": order_id, "status": "APPROVED", "ok": True}

    def fake_place(order_id):
        return {"order_id": order_id, "status": "SUBMITTED", "ok": True}

    monkeypatch.setattr(tools_write, "ApprovalContext", FakeApprovalContext, raising=False)
    monkeypatch.setattr(tools_write, "record_approval", fake_record_approval, raising=False)
    monkeypatch.setattr(tools_write, "approve_and_place_paper_order", fake_place, raising=False)

    fake_lakebase.roles["approver@example.com"] = "approver"
    resp = client.post(
        "/api/orders/ord_123/approve",
        headers={"x-forwarded-email": "approver@example.com"},
    )
    assert resp.status_code == 200
    assert captured["order_id"] == "ord_123"
    assert captured["approver_id"] == "approver@example.com"
