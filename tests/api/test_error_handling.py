"""Error-handling tests: backend exceptions never leak raw text to the browser."""

from __future__ import annotations


def test_backend_exception_text_not_leaked(client, fake_lakebase, monkeypatch):
    import agent.tools_retrieval as tools_retrieval

    secret = "sensitive-internal-host=db.internal password=hunter2"

    def boom(symbol):
        raise RuntimeError(secret)

    monkeypatch.setattr(tools_retrieval, "get_latest_signal", boom)

    resp = client.post(
        "/api/agent/chat",
        json={"message": "latest signal for NVDA"},
        headers={"x-forwarded-email": "trader@example.com"},
    )
    assert resp.status_code == 200
    assert secret not in resp.text
    assert "db.internal" not in resp.text
    assert "hunter2" not in resp.text
    assert "RuntimeError" not in resp.text
