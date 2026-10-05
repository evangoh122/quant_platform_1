"""tests/api/test_agent_chat_llm.py — API route tests for the LLM agent endpoint.

Tests the POST /api/agent/chat endpoint with the new LLM runtime. All tests
use fake transports — zero network calls, zero live credentials.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from agent.model_client import ModelClient, ModelError
from agent.runtime import AgentRuntime, ToolRegistry
from api.deps import AppUser


# ── fixtures ─────────────────────────────────────────────────────────────────
class FakeModelTransport:
    """Scripted model transport."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self._call_count = 0

    def query(self, **kwargs) -> dict:
        if self._call_count >= len(self._responses):
            raise ModelError("exhausted", "No more responses")
        text = self._responses[self._call_count]
        self._call_count += 1
        return {"text": text, "input_tokens": 100, "output_tokens": 50}


@pytest.fixture(autouse=True)
def _reset_circuit_breaker():
    """Reset circuit breaker between tests."""
    from api import deps
    deps._breaker.reset()
    deps._role_cache.clear()
    yield
    deps._breaker.reset()
    deps._role_cache.clear()


@pytest.fixture
def trader_user():
    """A non-degraded trader user for tests that need write access."""
    return AppUser(user_id="trader@example.com", role="trader", authenticated=True, degraded=False)


@pytest.fixture
def viewer_user():
    """A viewer user for read-only tests."""
    return AppUser(user_id="viewer@example.com", role="viewer", authenticated=True, degraded=False)


@pytest.fixture
def client(trader_user):
    """Test client with get_current_user overridden to return a trader."""
    from fastapi.testclient import TestClient
    from api.main import create_app
    from api.deps import get_current_user

    app = create_app()

    def _override_get_current_user():
        return trader_user

    app.dependency_overrides[get_current_user] = _override_get_current_user
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def viewer_client(viewer_user):
    """Test client with get_current_user overridden to return a viewer."""
    from fastapi.testclient import TestClient
    from api.main import create_app
    from api.deps import get_current_user

    app = create_app()

    def _override_get_current_user():
        return viewer_user

    app.dependency_overrides[get_current_user] = _override_get_current_user
    yield TestClient(app)
    app.dependency_overrides.clear()


# ── tests ─────────────────────────────────────────────────────────────────────
class TestAgentChatEndpoint:
    def test_read_only_retrieval(self, client):
        """Read-only retrieval works without write authorization."""
        transport = FakeModelTransport([
            json.dumps({"action": "retrieve", "tool": "get_latest_signal", "args": {"symbol": "NVDA"}}),
            json.dumps({"action": "final", "reply": "Latest NVDA signal: LONG (0.85)."}),
        ])

        def fake_retrieval(tool, args):
            return {"direction": "LONG", "probability": 0.85}

        with patch("api.routes.agent_chat._build_runtime") as mock_build:
            mock_build.return_value = AgentRuntime(
                model_client=ModelClient(transport=transport),
                tool_registry=ToolRegistry(retrieval_fn=fake_retrieval),
            )
            resp = client.post(
                "/api/agent/chat",
                json={"message": "What is the latest signal for NVDA?"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is True
        assert len(data["tool_calls"]) == 1
        assert data["tool_calls"][0]["name"] == "get_latest_signal"

    def test_write_with_authorization(self, client):
        """Write with proper authorization succeeds."""
        transport = FakeModelTransport([
            json.dumps({"action": "retrieve", "tool": "search_sec_filings", "args": {"symbol": "NVDA"}}),
            json.dumps({
                "action": "write",
                "tool": "save_research_note",
                "args": {"symbol": "NVDA", "note": "Risk analysis", "evidence_ids": ["chunk_001"]},
            }),
            json.dumps({"action": "final", "reply": "Note saved."}),
        ])

        def fake_retrieval(tool, args):
            return {"rows": [{"chunk_id": "chunk_001", "chunk_text": "Export controls."}]}

        def fake_write(tool, args, user_id=""):
            return {"note_id": "note_123", "symbol": "NVDA", "status": "saved"}

        with patch("api.routes.agent_chat._build_runtime") as mock_build:
            mock_build.return_value = AgentRuntime(
                model_client=ModelClient(transport=transport),
                tool_registry=ToolRegistry(retrieval_fn=fake_retrieval, write_fn=fake_write),
            )
            resp = client.post(
                "/api/agent/chat",
                json={
                    "message": "Research NVDA and save a note",
                    "write_authorization": {
                        "tool": "save_research_note",
                        "idempotency_key": "test-key-1",
                    },
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is True
        assert len(data["tool_calls"]) == 2

    def test_write_without_authorization_denied(self, client):
        """Write without authorization is denied — reply indicates the issue."""
        transport = FakeModelTransport([
            json.dumps({"action": "retrieve", "tool": "get_latest_signal", "args": {"symbol": "NVDA"}}),
            json.dumps({
                "action": "write",
                "tool": "save_research_note",
                "args": {"symbol": "NVDA", "note": "Test"},
            }),
        ])

        def fake_retrieval(tool, args):
            return {"direction": "LONG"}

        with patch("api.routes.agent_chat._build_runtime") as mock_build:
            mock_build.return_value = AgentRuntime(
                model_client=ModelClient(transport=transport),
                tool_registry=ToolRegistry(retrieval_fn=fake_retrieval),
            )
            resp = client.post(
                "/api/agent/chat",
                json={"message": "Research NVDA and save a note"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is True
        assert "not authorized" in data["reply"].lower()

    def test_model_failure_returns_clear_error(self, client):
        """Model failure returns a clear error, not a keyword fallback."""
        transport = FakeModelTransport([])  # No responses → will raise

        with patch("api.routes.agent_chat._build_runtime") as mock_build:
            mock_build.return_value = AgentRuntime(
                model_client=ModelClient(transport=transport),
                tool_registry=ToolRegistry(),
            )
            resp = client.post(
                "/api/agent/chat",
                json={"message": "Hello"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is False

    def test_degraded_user_write_blocked(self):
        """Degraded user (Lakebase unavailable) cannot write."""
        from fastapi.testclient import TestClient
        from api.main import create_app
        from api.deps import get_current_user

        degraded_user = AppUser(
            user_id="degraded@example.com", role="viewer",
            authenticated=True, degraded=True,
        )

        app = create_app()
        app.dependency_overrides[get_current_user] = lambda: degraded_user

        with TestClient(app) as degraded_client:
            resp = degraded_client.post(
                "/api/agent/chat",
                json={
                    "message": "Save a note",
                    "write_authorization": {
                        "tool": "save_research_note",
                        "idempotency_key": "key-1",
                    },
                },
            )

        assert resp.status_code == 503

    def test_unauthenticated_rejected(self):
        """Unauthenticated request is rejected."""
        from fastapi.testclient import TestClient
        from api.main import create_app
        from api.deps import get_current_user

        app = create_app()
        # Don't override get_current_user — use default (no header → 401)

        with TestClient(app) as unauth_client:
            resp = unauth_client.post(
                "/api/agent/chat",
                json={"message": "Hello"},
            )

        assert resp.status_code == 401