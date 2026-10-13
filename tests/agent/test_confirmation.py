"""tests/agent/test_confirmation.py — signed proposal token tests.

Covers the confirm-and-write token contract (``agent.confirmation``):
roundtrip, tamper (bad_signature), expiry, cross-user, malformed shapes, and
fail-closed behaviour when ``AGENT_CONFIRM_SECRET`` is unset (never signs,
never verifies). Pure functions only — no I/O beyond env manipulation.
"""
from __future__ import annotations

import base64
import json

import pytest

from agent.confirmation import (
    DEFAULT_TTL_SECONDS,
    ConfirmationError,
    derive_idempotency_key,
    issue_token,
    verify_token,
)

_SECRET = "unit-test-secret"


@pytest.fixture
def secret(monkeypatch):
    monkeypatch.setenv("AGENT_CONFIRM_SECRET", _SECRET)
    return _SECRET


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _tamper(token: str) -> str:
    """Return the token with its payload rewritten (signature left as-is)."""
    payload_b64, signature_b64 = token.split(".")
    pad = "=" * (-len(payload_b64) % 4)
    raw = base64.urlsafe_b64decode(payload_b64 + pad)
    payload = json.loads(raw.decode("utf-8"))
    payload["user_id"] = "mallory"
    return f"{_b64url(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8'))}.{signature_b64}"


class TestRoundtrip:
    def test_issue_and_verify(self, secret):
        token = issue_token(
            "alice", "save_research_note",
            {"symbol": "NVDA", "note": "Risk"}, "trace-1", now=1_000_000.0,
        )
        payload = verify_token(token, "alice", now=1_000_001.0)

        assert payload.v == 1
        assert payload.user_id == "alice"
        assert payload.tool == "save_research_note"
        assert payload.args == {"symbol": "NVDA", "note": "Risk"}
        assert payload.trace_id == "trace-1"
        assert payload.exp == 1_000_000 + DEFAULT_TTL_SECONDS

    def test_token_is_opaque_two_segments(self, secret):
        token = issue_token("alice", "add_to_watchlist", {"symbol": "AMD"}, "t", now=0.0)
        parts = token.split(".")
        assert len(parts) == 2
        assert all(parts)

    def test_idempotency_key_deterministic_across_reproposal(self, secret):
        """Re-proposing the same (user, tool, args) yields the same key."""
        args = {"symbol": "NVDA", "note": "Same note"}
        first = verify_token(
            issue_token("alice", "save_research_note", args, "t1", now=1.0),
            "alice", now=1.0,
        )
        second = verify_token(
            issue_token("alice", "save_research_note", dict(args), "t2", now=2.0),
            "alice", now=2.0,
        )
        assert first.idempotency_key == second.idempotency_key
        assert first.idempotency_key == derive_idempotency_key(
            "alice", "save_research_note", args,
        )

    def test_idempotency_key_changes_with_args(self, secret):
        key_a = derive_idempotency_key("alice", "save_research_note", {"symbol": "NVDA", "note": "A"})
        key_b = derive_idempotency_key("alice", "save_research_note", {"symbol": "NVDA", "note": "B"})
        key_c = derive_idempotency_key("bob", "save_research_note", {"symbol": "NVDA", "note": "A"})
        assert len({key_a, key_b, key_c}) == 3


class TestTamperAndAuthn:
    def test_tampered_payload_rejected(self, secret):
        token = issue_token("alice", "save_research_note", {"symbol": "NVDA", "note": "x"}, "t", now=10.0)
        with pytest.raises(ConfirmationError) as exc:
            verify_token(_tamper(token), "alice", now=10.0)
        assert exc.value.code == "bad_signature"

    def test_wrong_user_rejected(self, secret):
        token = issue_token("alice", "save_research_note", {"symbol": "NVDA", "note": "x"}, "t", now=10.0)
        with pytest.raises(ConfirmationError) as exc:
            verify_token(token, "bob", now=10.0)
        assert exc.value.code == "wrong_user"

    def test_expired_rejected(self, secret):
        token = issue_token("alice", "save_research_note", {"symbol": "NVDA", "note": "x"}, "t", now=10.0)
        with pytest.raises(ConfirmationError) as exc:
            verify_token(token, "alice", now=10.0 + DEFAULT_TTL_SECONDS + 1)
        assert exc.value.code == "expired"

    def test_valid_token_still_accepted_just_before_expiry(self, secret):
        token = issue_token("alice", "save_research_note", {"symbol": "NVDA", "note": "x"}, "t", now=10.0)
        payload = verify_token(token, "alice", now=10.0 + DEFAULT_TTL_SECONDS - 1)
        assert payload.user_id == "alice"


class TestNoSecret:
    def test_issue_never_signs_without_secret(self, monkeypatch):
        monkeypatch.delenv("AGENT_CONFIRM_SECRET", raising=False)
        with pytest.raises(ConfirmationError) as exc:
            issue_token("alice", "save_research_note", {"symbol": "NVDA"}, "t", now=0.0)
        assert exc.value.code == "unavailable"

    def test_verify_never_accepts_without_secret(self, monkeypatch):
        monkeypatch.setenv("AGENT_CONFIRM_SECRET", _SECRET)
        token = issue_token("alice", "save_research_note", {"symbol": "NVDA"}, "t", now=0.0)
        monkeypatch.delenv("AGENT_CONFIRM_SECRET", raising=False)
        with pytest.raises(ConfirmationError) as exc:
            verify_token(token, "alice", now=0.0)
        assert exc.value.code == "unavailable"

    def test_empty_secret_is_unset(self, monkeypatch):
        monkeypatch.setenv("AGENT_CONFIRM_SECRET", "")
        with pytest.raises(ConfirmationError) as exc:
            issue_token("alice", "save_research_note", {"symbol": "NVDA"}, "t", now=0.0)
        assert exc.value.code == "unavailable"


class TestMalformed:
    @pytest.mark.parametrize("token", [
        "",
        "not-a-token",
        "a.b.c",
        "onlyonesegment",
        ".",
        "a.",
        ".b",
        "@@@@.@@@@",
    ])
    def test_malformed_tokens_rejected(self, secret, token):
        with pytest.raises(ConfirmationError) as exc:
            verify_token(token, "alice", now=0.0)
        assert exc.value.code == "malformed"

    def test_non_json_payload_rejected(self, secret):
        token = f"{_b64url(b'not json')}.{_b64url(b'0' * 32)}"
        with pytest.raises(ConfirmationError) as exc:
            verify_token(token, "alice", now=0.0)
        assert exc.value.code in ("malformed", "bad_signature")

    @pytest.mark.parametrize("mutate", [
        lambda p: {**p, "v": 2},
        lambda p: {k: v for k, v in p.items() if k != "exp"},
        lambda p: {**p, "exp": "soon"},
        lambda p: {**p, "args": ["not", "a", "dict"]},
        lambda p: {**p, "user_id": 7},
        lambda p: {**p, "idempotency_key": ""},
    ])
    def test_defective_payload_shapes_rejected(self, secret, mutate):
        """Payload shape defects are malformed (or bad_signature if rewritten)."""
        base = {
            "v": 1, "user_id": "alice", "tool": "save_research_note",
            "args": {"symbol": "NVDA"}, "idempotency_key": "k",
            "trace_id": "t", "exp": 100,
        }
        mutated = mutate(base)
        payload_bytes = json.dumps(mutated, sort_keys=True, separators=(",", ":")).encode("utf-8")
        # Sign correctly so only the payload shape can cause rejection.
        import hashlib
        import hmac
        signature = hmac.new(_SECRET.encode("utf-8"), payload_bytes, hashlib.sha256).digest()
        token = f"{_b64url(payload_bytes)}.{_b64url(signature)}"
        with pytest.raises(ConfirmationError) as exc:
            verify_token(token, "alice", now=0.0)
        assert exc.value.code == "malformed"
