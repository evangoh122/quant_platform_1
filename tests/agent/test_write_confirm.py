"""tests/agent/test_write_confirm.py — confirm-and-write proposal tests.

The write branch of ``agent.runtime``: a write without request-scoped
authorization must be PROPOSED (signed token + ``pending_action``) and never
executed; role/public-demo refusals run before the authorization check; with
no ``AGENT_CONFIRM_SECRET`` the turn fails closed with
``confirmation_unavailable`` and no proposal. All fake transports.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import pytest

from agent.confirmation import verify_token
from agent.model_client import ModelClient, ModelError, ModelResponse
from agent.runtime import (
    AgentRuntime,
    AgentResult,
    AuditEntry,
    AuditSink,
    RuntimeConfig,
    ToolRegistry,
)


class FakeModelTransport:
    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self._call_count = 0

    def query(self, **kwargs) -> dict:
        if self._call_count >= len(self._responses):
            raise ModelError("exhausted", "No more scripted responses")
        text = self._responses[self._call_count]
        self._call_count += 1
        return {"text": text, "input_tokens": 100, "output_tokens": 50}


class FakeAuditSink:
    def __init__(self):
        self.entries: List[AuditEntry] = []

    def emit(self, entry: AuditEntry) -> None:
        self.entries.append(entry)


class FakeRetrievalFn:
    def __init__(self, results: Optional[Dict[str, Any]] = None):
        self._results = results or {}
        self.call_count = 0

    def __call__(self, tool: str, args: dict) -> dict:
        self.call_count += 1
        return self._results.get(tool, {})


class FakeWriteFn:
    def __init__(self, result: Optional[Dict[str, Any]] = None):
        self._result = result or {"note_id": "note_123", "symbol": "NVDA", "status": "saved"}
        self.call_count = 0
        self.last_args = None
        self.last_user_id = None

    def __call__(self, tool: str, args: dict, *, user_id: str) -> dict:
        self.call_count += 1
        self.last_args = args
        self.last_user_id = user_id
        return self._result


def _make_runtime(model_responses, retrieval_fn=None, write_fn=None):
    transport = FakeModelTransport(model_responses)
    model_client = ModelClient(transport=transport)
    sink = FakeAuditSink()
    registry = ToolRegistry(retrieval_fn=retrieval_fn, write_fn=write_fn)
    runtime = AgentRuntime(
        model_client=model_client, tool_registry=registry, audit_sink=sink,
    )
    return runtime, sink


def _write_turn(note: str = "Export controls remain a key risk") -> list[str]:
    return [
        json.dumps({"action": "retrieve", "tool": "get_latest_signal", "args": {"symbol": "NVDA"}}),
        json.dumps({
            "action": "write",
            "tool": "save_research_note",
            "args": {"symbol": "NVDA", "note": note},
        }),
    ]


class TestProposal:
    def test_write_proposal_returns_pending_action_and_executes_nothing(self, monkeypatch):
        """A write turn without authorization proposes; it executes NOTHING."""
        monkeypatch.setenv("AGENT_CONFIRM_SECRET", "unit-test-secret")
        write_fn = FakeWriteFn()
        runtime, sink = _make_runtime(
            _write_turn(),
            retrieval_fn=FakeRetrievalFn({"get_latest_signal": {"direction": "LONG"}}),
            write_fn=write_fn,
        )

        result = runtime.run(
            "Research NVDA and save a note",
            user_id="trader_1", role="trader", write_authorization=None,
        )

        assert result.error_code is None
        assert write_fn.call_count == 0
        assert result.tool_calls == [
            {
                "name": "get_latest_signal",
                "arguments": {"symbol": "NVDA"},
                "result": {"direction": "LONG"},
                "ok": True,
            }
        ]
        pending = result.pending_action
        assert pending is not None
        assert pending["tool"] == "save_research_note"
        assert pending["args"]["symbol"] == "NVDA"
        assert pending["args"]["note"] == "Export controls remain a key risk"
        assert pending["token"]
        assert pending["expires_at"]
        assert "NVDA" in pending["summary"]

    def test_proposal_token_is_signed_and_bound_to_user(self, monkeypatch):
        monkeypatch.setenv("AGENT_CONFIRM_SECRET", "unit-test-secret")
        runtime, _ = _make_runtime(
            _write_turn(),
            retrieval_fn=FakeRetrievalFn({"get_latest_signal": {}}),
            write_fn=FakeWriteFn(),
        )
        result = runtime.run(
            "Save a note", user_id="trader_1", role="trader", write_authorization=None,
        )
        payload = verify_token(result.pending_action["token"], "trader_1")
        assert payload.user_id == "trader_1"
        assert payload.tool == "save_research_note"
        assert payload.trace_id == result.trace_id
        assert payload.idempotency_key

    def test_reproposing_same_note_yields_same_idempotency_key(self, monkeypatch):
        monkeypatch.setenv("AGENT_CONFIRM_SECRET", "unit-test-secret")
        keys = []
        for _ in range(2):
            runtime, _ = _make_runtime(
                _write_turn(note="Same note text"),
                retrieval_fn=FakeRetrievalFn({"get_latest_signal": {}}),
                write_fn=FakeWriteFn(),
            )
            result = runtime.run(
                "Save a note", user_id="trader_1", role="trader", write_authorization=None,
            )
            payload = verify_token(result.pending_action["token"], "trader_1")
            keys.append(payload.idempotency_key)
        assert keys[0] == keys[1]

    def test_write_proposed_audit_entry_emitted(self, monkeypatch):
        monkeypatch.setenv("AGENT_CONFIRM_SECRET", "unit-test-secret")
        runtime, sink = _make_runtime(
            _write_turn(),
            retrieval_fn=FakeRetrievalFn({"get_latest_signal": {}}),
            write_fn=FakeWriteFn(),
        )
        runtime.run("Save a note", user_id="trader_1", role="trader", write_authorization=None)
        actions = [e.action for e in sink.entries]
        assert "write_proposed" in actions

    def test_no_secret_fails_closed_without_proposal(self, monkeypatch):
        monkeypatch.delenv("AGENT_CONFIRM_SECRET", raising=False)
        write_fn = FakeWriteFn()
        runtime, sink = _make_runtime(
            _write_turn(),
            retrieval_fn=FakeRetrievalFn({"get_latest_signal": {}}),
            write_fn=write_fn,
        )
        result = runtime.run(
            "Save a note", user_id="trader_1", role="trader", write_authorization=None,
        )
        assert result.error_code == "confirmation_unavailable"
        assert result.pending_action is None
        assert write_fn.call_count == 0
        assert "not authorized" in result.reply.lower()
        assert "confirmation_unavailable" in [e.validation_outcome for e in sink.entries]


class TestGuardOrdering:
    def test_viewer_role_denied_not_proposed(self, monkeypatch):
        monkeypatch.setenv("AGENT_CONFIRM_SECRET", "unit-test-secret")
        write_fn = FakeWriteFn()
        runtime, _ = _make_runtime(
            _write_turn(),
            retrieval_fn=FakeRetrievalFn({"get_latest_signal": {}}),
            write_fn=write_fn,
        )
        result = runtime.run(
            "Save a note", user_id="viewer_1", role="viewer", write_authorization=None,
        )
        assert result.error_code == "role_denied"
        assert result.pending_action is None
        assert write_fn.call_count == 0

    def test_viewer_role_denied_even_with_authorization(self, monkeypatch):
        monkeypatch.setenv("AGENT_CONFIRM_SECRET", "unit-test-secret")
        from api.schemas import WriteAuthorization

        write_fn = FakeWriteFn()
        runtime, _ = _make_runtime(
            _write_turn(),
            retrieval_fn=FakeRetrievalFn({"get_latest_signal": {}}),
            write_fn=write_fn,
        )
        result = runtime.run(
            "Save a note", user_id="viewer_1", role="viewer",
            write_authorization=WriteAuthorization(
                tool="save_research_note", idempotency_key="k1",
            ),
        )
        assert result.error_code == "role_denied"
        assert write_fn.call_count == 0

    def test_public_demo_denied_not_proposed(self, monkeypatch):
        monkeypatch.setenv("AGENT_CONFIRM_SECRET", "unit-test-secret")
        monkeypatch.setenv("PUBLIC_DEMO", "1")
        write_fn = FakeWriteFn()
        runtime, _ = _make_runtime(
            _write_turn(),
            retrieval_fn=FakeRetrievalFn({"get_latest_signal": {}}),
            write_fn=write_fn,
        )
        result = runtime.run(
            "Save a note", user_id="trader_1", role="trader", write_authorization=None,
        )
        assert result.error_code == "public_demo"
        assert result.pending_action is None
        assert write_fn.call_count == 0

    def test_tool_mismatch_still_refused(self, monkeypatch):
        monkeypatch.setenv("AGENT_CONFIRM_SECRET", "unit-test-secret")
        from api.schemas import WriteAuthorization

        write_fn = FakeWriteFn()
        runtime, _ = _make_runtime(
            _write_turn(),
            retrieval_fn=FakeRetrievalFn({"get_latest_signal": {}}),
            write_fn=write_fn,
        )
        result = runtime.run(
            "Save a note", user_id="trader_1", role="trader",
            write_authorization=WriteAuthorization(
                tool="add_to_watchlist", idempotency_key="k1",
            ),
        )
        assert result.error_code == "write_not_authorized"
        assert result.pending_action is None
        assert write_fn.call_count == 0


class TestProposalValidation:
    def test_proposal_is_evidence_bound(self, monkeypatch):
        """A note referencing evidence outside the trace is refused before proposing."""
        monkeypatch.setenv("AGENT_CONFIRM_SECRET", "unit-test-secret")
        sec_result = {"rows": [{"chunk_id": "chunk_001", "chunk_text": "Risk analysis."}]}
        write_fn = FakeWriteFn()
        model_responses = [
            json.dumps({"action": "retrieve", "tool": "search_sec_filings", "args": {"symbol": "NVDA"}}),
            json.dumps({
                "action": "write",
                "tool": "save_research_note",
                "args": {"symbol": "NVDA", "note": "Based on evidence", "evidence_ids": ["chunk_999"]},
            }),
        ]
        runtime, _ = _make_runtime(
            model_responses,
            retrieval_fn=FakeRetrievalFn({"search_sec_filings": sec_result}),
            write_fn=write_fn,
        )
        result = runtime.run(
            "Research and save", user_id="trader_1", role="trader", write_authorization=None,
        )
        assert result.error_code == "no_evidence"
        assert result.pending_action is None
        assert write_fn.call_count == 0

    def test_proposed_args_carry_evidence_ids(self, monkeypatch):
        monkeypatch.setenv("AGENT_CONFIRM_SECRET", "unit-test-secret")
        sec_result = {"rows": [{"chunk_id": "chunk_001", "chunk_text": "Risk analysis."}]}
        model_responses = [
            json.dumps({"action": "retrieve", "tool": "search_sec_filings", "args": {"symbol": "NVDA"}}),
            json.dumps({
                "action": "write",
                "tool": "save_research_note",
                "args": {"symbol": "NVDA", "note": "Based on evidence", "evidence_ids": ["chunk_001"]},
            }),
        ]
        runtime, _ = _make_runtime(
            model_responses,
            retrieval_fn=FakeRetrievalFn({"search_sec_filings": sec_result}),
            write_fn=FakeWriteFn(),
        )
        result = runtime.run(
            "Research and save", user_id="trader_1", role="trader", write_authorization=None,
        )
        assert result.pending_action is not None
        assert result.pending_action["args"]["evidence_ids"] == ["chunk_001"]

    def test_write_first_action_still_blocked(self, monkeypatch):
        monkeypatch.setenv("AGENT_CONFIRM_SECRET", "unit-test-secret")
        write_fn = FakeWriteFn()
        model_responses = [
            json.dumps({
                "action": "write",
                "tool": "save_research_note",
                "args": {"symbol": "NVDA", "note": "Skip research"},
            }),
        ]
        runtime, _ = _make_runtime(model_responses, write_fn=write_fn)
        result = runtime.run(
            "Save a note", user_id="trader_1", role="trader", write_authorization=None,
        )
        assert result.error_code == "write_first_action"
        assert result.pending_action is None
        assert write_fn.call_count == 0
