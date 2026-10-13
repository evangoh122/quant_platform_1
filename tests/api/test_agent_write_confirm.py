"""tests/api/test_agent_write_confirm.py — chat confirm-and-write route tests.

Two-step write flow over the API: the chat turn returns a signed proposal
(``pending_action``); a request carrying ``confirm_token`` executes exactly
that proposal through the closed tool registry — no LLM call, no client-supplied
args or idempotency keys. Also covers ``GET /api/notes`` and the watchlist read
path. All fakes — zero network calls, zero live credentials.
"""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

import pytest

from agent.confirmation import issue_token
from agent.model_client import ModelClient, ModelError
from agent.runtime import AuditEntry, ToolRegistry
from api.deps import AppUser

USER_ID = "trader@example.com"
_SECRET = "unit-test-secret"


# ── fakes ────────────────────────────────────────────────────────────────────
class FakeWriteFn:
    """Records calls; reports replay from the second call onward."""

    def __init__(self, result: Optional[Dict[str, Any]] = None):
        self.calls: List[Dict[str, Any]] = []
        self._result = result

    def __call__(self, tool: str, args: dict, *, user_id: str) -> dict:
        self.calls.append({"tool": tool, "args": dict(args), "user_id": user_id})
        if self._result is not None:
            return dict(self._result)
        replay = len(self.calls) > 1
        return {
            "note_id": "note_123",
            "symbol": "NVDA",
            "status": "saved",
            "replay": replay,
        }


class AuditCollector:
    def __init__(self):
        self.entries: List[AuditEntry] = []

    def __call__(self, entry: AuditEntry) -> None:
        self.entries.append(entry)

    @property
    def actions(self) -> List[str]:
        return [e.action for e in self.entries]


class FakeModelTransport:
    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.call_count = 0

    def query(self, **kwargs) -> dict:
        if self.call_count >= len(self._responses):
            raise ModelError("exhausted", "No more responses")
        text = self._responses[self.call_count]
        self.call_count += 1
        return {"text": text, "input_tokens": 100, "output_tokens": 50}


class FakeAgentStore:
    """Minimal Lakebase stand-in for research_notes / watchlists reads."""

    def __init__(self):
        self.users: Dict[str, str] = {}
        self.watchlists: List[dict] = []
        self.notes: List[dict] = []
        self.actions: List[tuple] = []
        self._last: List[tuple] = []

    @contextmanager
    def transaction(self):
        yield self

    @contextmanager
    def cursor(self):
        yield self

    def execute(self, query: str, params=None):
        q = " ".join(query.split()).lower()
        params = tuple(params or ())
        self._last = []
        if q.startswith("insert into users"):
            user_id = params[0]
            role = params[2] if len(params) >= 3 else "viewer"
            if user_id not in self.users:
                self.users[user_id] = role
                self._last = [(role,)]
            return list(self._last)
        if q.startswith("insert into watchlists"):
            watchlist_id, user_id, symbol = params[0], params[1], params[2]
            for row in self.watchlists:
                if row["user_id"] == user_id and row["symbol"] == symbol:
                    self._last = [(row["watchlist_id"], row["symbol"])]
                    return []
            self.watchlists.append({
                "watchlist_id": watchlist_id, "user_id": user_id,
                "symbol": symbol, "created_at": "2024-06-01T00:00:00",
            })
            self._last = [(watchlist_id, symbol)]
            return []
        if q.startswith("insert into agent_actions"):
            self.actions.append(params)
            return []
        if q.startswith("select symbol, created_at from watchlists"):
            user_id = params[0]
            rows = [w for w in self.watchlists if w["user_id"] == user_id]
            rows.sort(key=lambda w: w["created_at"], reverse=True)
            self._last = [(w["symbol"], w["created_at"]) for w in rows]
            return list(self._last)
        if q.startswith("select note_id, symbol, note_text, created_at from research_notes"):
            user_id = params[0]
            rows = [n for n in self.notes if n["user_id"] == user_id]
            rows.sort(key=lambda n: n["created_at"], reverse=True)
            self._last = [
                (n["note_id"], n["symbol"], n["note_text"], n["created_at"])
                for n in rows
            ]
            return list(self._last)
        return []

    def fetchone(self, query: Optional[str] = None, params=None):
        return self._last[0] if self._last else None

    def fetchall(self):
        return list(self._last)


# ── fixtures ─────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _reset_resilience():
    from api import deps

    deps._breaker.reset()
    deps._role_cache.clear()
    yield
    deps._breaker.reset()
    deps._role_cache.clear()


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    import os

    from api.demo import _is_unsafe_key

    monkeypatch.delenv("PUBLIC_DEMO", raising=False)
    # Deterministic env: strip ambient vars that public-demo validation rejects.
    for key in list(os.environ):
        if key == "PUBLIC_DEMO":
            continue
        if _is_unsafe_key(key, os.environ.get(key, "")):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AGENT_CONFIRM_SECRET", _SECRET)


@pytest.fixture
def trader_user():
    return AppUser(user_id=USER_ID, role="trader", authenticated=True, degraded=False)


@pytest.fixture
def client(trader_user):
    from fastapi.testclient import TestClient

    from api.deps import get_current_user
    from api.main import create_app

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: trader_user
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def write_fn():
    return FakeWriteFn()


@pytest.fixture
def audit(monkeypatch) -> AuditCollector:
    collector = AuditCollector()
    monkeypatch.setattr("api.routes.agent_chat._emit_audit", collector)
    return collector


@pytest.fixture
def registry(monkeypatch, write_fn) -> ToolRegistry:
    registry = ToolRegistry(write_fn=write_fn)
    monkeypatch.setattr("api.routes.agent_chat._build_tool_registry", lambda: registry)
    return registry


def _token(user_id: str = USER_ID, *, now: Optional[float] = None, ttl: int = 600) -> str:
    return issue_token(
        user_id,
        "save_research_note",
        {"symbol": "NVDA", "note": "Export controls remain a key risk", "evidence_ids": ["chunk_001"]},
        "trace-confirm-1",
        now=now if now is not None else time.time(),
        ttl_seconds=ttl,
    )


# ── confirm path ─────────────────────────────────────────────────────────────
class TestConfirmWrite:
    def test_confirm_executes_exactly_once(self, client, registry, write_fn, audit):
        resp = client.post("/api/agent/chat", json={"confirm_token": _token()})

        assert resp.status_code == 200
        data = resp.json()
        assert len(write_fn.calls) == 1
        call = write_fn.calls[0]
        assert call["tool"] == "save_research_note"
        assert call["user_id"] == USER_ID
        assert call["args"]["symbol"] == "NVDA"
        assert call["args"]["idempotency_key"]
        assert data["write_result"]["note_id"] == "note_123"
        assert data["write_result"]["status"] == "saved"
        assert data["write_result"]["trace_id"] == "trace-confirm-1"
        assert "write_confirmed" in audit.actions

    def test_second_confirm_replays_same_key(self, client, registry, write_fn, audit):
        token = _token()
        first = client.post("/api/agent/chat", json={"confirm_token": token})
        second = client.post("/api/agent/chat", json={"confirm_token": token})

        assert first.status_code == 200
        assert second.status_code == 200
        assert len(write_fn.calls) == 2
        assert (
            write_fn.calls[0]["args"]["idempotency_key"]
            == write_fn.calls[1]["args"]["idempotency_key"]
        )
        assert first.json()["write_result"]["replay"] is False
        assert second.json()["write_result"]["replay"] is True

    def test_client_cannot_supply_args_or_keys(self, client, registry, write_fn):
        """An args/key-carrying confirm body is rejected before any execution."""
        resp = client.post("/api/agent/chat", json={
            "confirm_token": _token(),
            "args": {"symbol": "AAPL", "note": "hijack"},
            "idempotency_key": "attacker-key",
        })
        assert resp.status_code == 422
        assert write_fn.calls == []

    def test_wrong_user_token_forbidden_and_audited(self, client, registry, write_fn, audit):
        resp = client.post("/api/agent/chat", json={"confirm_token": _token(user_id="other@example.com")})
        assert resp.status_code == 403
        assert write_fn.calls == []
        rejected = [e for e in audit.entries if e.action == "write_rejected"]
        assert rejected and rejected[0].validation_outcome == "wrong_user"

    def test_expired_token_gone(self, client, registry, write_fn, audit):
        resp = client.post("/api/agent/chat", json={
            "confirm_token": _token(now=time.time() - 4000),
        })
        assert resp.status_code == 410
        assert write_fn.calls == []
        rejected = [e for e in audit.entries if e.action == "write_rejected"]
        assert rejected and rejected[0].validation_outcome == "expired"

    def test_tampered_token_bad_request(self, client, registry, write_fn, audit):
        import base64

        token = _token()
        payload_b64, signature_b64 = token.split(".")
        pad = "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + pad))
        payload["args"]["note"] = "Tampered note text"
        tampered_payload = base64.urlsafe_b64encode(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).decode("ascii").rstrip("=")

        resp = client.post("/api/agent/chat", json={
            "confirm_token": f"{tampered_payload}.{signature_b64}",
        })
        assert resp.status_code == 400
        assert write_fn.calls == []
        rejected = [e for e in audit.entries if e.action == "write_rejected"]
        assert rejected and rejected[0].validation_outcome == "bad_signature"

    def test_confirm_and_write_authorization_rejected(self, client, registry, write_fn):
        resp = client.post("/api/agent/chat", json={
            "message": "Save a note",
            "confirm_token": _token(),
            "write_authorization": {"tool": "save_research_note", "idempotency_key": "k"},
        })
        assert resp.status_code == 422
        assert write_fn.calls == []

    def test_degraded_confirm_503(self, monkeypatch, registry, write_fn, audit):
        from fastapi.testclient import TestClient

        from api.deps import get_current_user
        from api.main import create_app

        degraded = AppUser(
            user_id=USER_ID, role="trader", authenticated=True, degraded=True,
        )
        app = create_app()
        app.dependency_overrides[get_current_user] = lambda: degraded
        with TestClient(app) as degraded_client:
            resp = degraded_client.post("/api/agent/chat", json={"confirm_token": _token()})

        assert resp.status_code == 503
        assert write_fn.calls == []
        assert "write_rejected" in audit.actions

    def test_public_demo_confirm_forbidden(self, monkeypatch, registry, write_fn, audit):
        from fastapi.testclient import TestClient

        from api.deps import get_current_user
        from api.main import create_app

        demo_user = AppUser(
            user_id="public-demo", role="viewer", authenticated=False,
        )
        # App is constructed outside demo mode (a demo deployment never carries
        # AGENT_CONFIRM_SECRET); the request-time demo re-check must still fire.
        app = create_app()
        app.dependency_overrides[get_current_user] = lambda: demo_user
        monkeypatch.setenv("PUBLIC_DEMO", "1")
        with TestClient(app) as demo_client:
            resp = demo_client.post("/api/agent/chat", json={
                "confirm_token": _token(user_id="public-demo"),
            })

        assert resp.status_code == 403
        assert write_fn.calls == []
        assert "write_rejected" in audit.actions

    def test_no_llm_call_on_confirm(self, monkeypatch, client, registry, write_fn):
        def _boom():
            raise AssertionError("LLM runtime must not run on confirm")

        monkeypatch.setattr("api.routes.agent_chat._build_runtime", _boom)
        resp = client.post("/api/agent/chat", json={"confirm_token": _token()})
        assert resp.status_code == 200
        assert len(write_fn.calls) == 1


class TestProposalEndpoint:
    def test_normal_path_maps_pending_action(self, monkeypatch, client, audit):
        from agent.runtime import AgentRuntime

        monkeypatch.delenv("AGENT_CONFIRM_SECRET", raising=False)
        monkeypatch.setenv("AGENT_CONFIRM_SECRET", _SECRET)
        transport = FakeModelTransport([
            json.dumps({"action": "retrieve", "tool": "get_latest_signal", "args": {"symbol": "NVDA"}}),
            json.dumps({
                "action": "write",
                "tool": "save_research_note",
                "args": {"symbol": "NVDA", "note": "Risk analysis"},
            }),
        ])

        def fake_retrieval(tool, args):
            return {"direction": "LONG"}

        monkeypatch.setattr(
            "api.routes.agent_chat._build_runtime",
            lambda: AgentRuntime(
                model_client=ModelClient(transport=transport),
                tool_registry=ToolRegistry(retrieval_fn=fake_retrieval),
            ),
        )
        resp = client.post("/api/agent/chat", json={"message": "Research NVDA and save a note"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["pending_action"]["tool"] == "save_research_note"
        assert data["pending_action"]["args"]["symbol"] == "NVDA"
        assert data["pending_action"]["token"]
        assert data["write_result"] is None

    def test_no_secret_fails_closed(self, monkeypatch, client):
        from agent.runtime import AgentRuntime

        monkeypatch.delenv("AGENT_CONFIRM_SECRET", raising=False)
        transport = FakeModelTransport([
            json.dumps({"action": "retrieve", "tool": "get_latest_signal", "args": {"symbol": "NVDA"}}),
            json.dumps({
                "action": "write",
                "tool": "save_research_note",
                "args": {"symbol": "NVDA", "note": "Risk analysis"},
            }),
        ])

        def fake_retrieval(tool, args):
            return {"direction": "LONG"}

        monkeypatch.setattr(
            "api.routes.agent_chat._build_runtime",
            lambda: AgentRuntime(
                model_client=ModelClient(transport=transport),
                tool_registry=ToolRegistry(retrieval_fn=fake_retrieval),
            ),
        )
        resp = client.post("/api/agent/chat", json={"message": "Research NVDA and save a note"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["pending_action"] is None
        assert "not authorized" in data["reply"].lower()


# ── notes + watchlist read paths ─────────────────────────────────────────────
class TestNotes:
    def test_notes_returns_only_callers_notes(self, monkeypatch, client, trader_user):
        store = FakeAgentStore()
        store.notes = [
            {"note_id": "note_a1", "user_id": USER_ID, "symbol": "NVDA",
             "note_text": "Mine first", "created_at": "2024-06-02T00:00:00"},
            {"note_id": "note_a2", "user_id": USER_ID, "symbol": "AMD",
             "note_text": "Mine second", "created_at": "2024-06-03T00:00:00"},
            {"note_id": "note_b1", "user_id": "other@example.com", "symbol": "TSLA",
             "note_text": "Not mine", "created_at": "2024-06-04T00:00:00"},
        ]
        monkeypatch.setattr("db.lakebase.get_lakebase", lambda: store)

        resp = client.get("/api/notes")

        assert resp.status_code == 200
        data = resp.json()
        assert [n["note_id"] for n in data["data"]] == ["note_a2", "note_a1"]
        assert all(n["note_id"] != "note_b1" for n in data["data"])
        assert data["data"][0]["note_text"] == "Mine second"
        assert data["freshness"]["state"] == "fresh"

    def test_notes_degraded_empty(self, monkeypatch):
        from fastapi.testclient import TestClient

        from api.deps import get_current_user
        from api.main import create_app

        degraded = AppUser(
            user_id=USER_ID, role="trader", authenticated=True, degraded=True,
        )
        app = create_app()
        app.dependency_overrides[get_current_user] = lambda: degraded
        with TestClient(app) as degraded_client:
            resp = degraded_client.get("/api/notes")

        assert resp.status_code == 200
        data = resp.json()
        assert data["data"] == []
        assert data["empty"] is True

    def test_notes_unavailable_db_degrades_to_empty(self, monkeypatch, client):
        def _boom():
            raise RuntimeError("lakebase down")

        monkeypatch.setattr("db.lakebase.get_lakebase", _boom)
        resp = client.get("/api/notes")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"] == []
        assert data["empty"] is True
        assert data["freshness"]["state"] == "unavailable"

    def test_notes_works_in_public_demo(self, monkeypatch):
        from fastapi.testclient import TestClient

        from api.main import create_app

        monkeypatch.setenv("PUBLIC_DEMO", "1")
        # A demo deployment never carries write-confirmation secrets.
        monkeypatch.delenv("AGENT_CONFIRM_SECRET", raising=False)
        app = create_app()
        with TestClient(app) as demo_client:
            resp = demo_client.get("/api/notes")

        assert resp.status_code == 200
        assert resp.json()["data"] == []


class TestWatchlistFromAgent:
    def test_watchlist_get_returns_item_added_via_agent(self, monkeypatch, client):
        store = FakeAgentStore()
        monkeypatch.setattr("db.lakebase.get_lakebase", lambda: store)
        monkeypatch.setattr("agent.tools_write.get_lakebase", lambda: store)
        monkeypatch.setattr("agent.tools_retrieval.get_lakebase", lambda: store)

        registry = ToolRegistry()
        result = registry.execute("add_to_watchlist", {"symbol": "AMD"}, user_id=USER_ID)
        assert result["symbol"] == "AMD"

        resp = client.get("/api/watchlists")
        assert resp.status_code == 200
        data = resp.json()
        assert [w["symbol"] for w in data["data"]] == ["AMD"]
