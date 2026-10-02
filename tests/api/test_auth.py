"""Authentication tests: the trusted header, spoof resistance, and fail-closed 503."""

from __future__ import annotations


def test_no_auth_header_returns_401(client, fake_lakebase):
    resp = client.get("/api/signals")
    assert resp.status_code == 401


def test_spoofed_headers_without_forwarded_email_return_401(client, fake_lakebase):
    resp = client.get(
        "/api/signals",
        headers={
            "x-forwarded-user": "attacker@example.com",
            "x-databricks-user": "attacker@example.com",
            "x-databricks-user-email": "attacker@example.com",
        },
    )
    assert resp.status_code == 401


def test_unknown_user_provisioned_as_viewer(client, fake_lakebase):
    resp = client.get(
        "/api/analytics", headers={"x-forwarded-email": "new@example.com"}
    )
    assert resp.status_code == 200
    assert fake_lakebase.roles["new@example.com"] == "viewer"


def test_db_failure_in_role_lookup_returns_503(client, fake_lakebase):
    fake_lakebase.fail = True
    resp = client.get(
        "/api/signals", headers={"x-forwarded-email": "user@example.com"}
    )
    assert resp.status_code == 503
    assert "identity service unavailable" in resp.json()["detail"]
