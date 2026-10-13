"""agent/confirmation.py — stateless signed proposal tokens (confirm-and-write).

A chat write is a two-step flow: the agent PROPOSES, the user CONFIRMS in the
UI, the server EXECUTES exactly what was proposed. The proposal is carried by a
stateless, signed token:

    token = base64url(payload) "." base64url(HMAC-SHA256(secret, payload))

where ``payload`` is canonical JSON::

    {"v": 1, "user_id": ..., "tool": ..., "args": {...},
     "idempotency_key": ..., "trace_id": ..., "exp": <unix seconds>}

Fail-closed: the signing secret comes from the ``AGENT_CONFIRM_SECRET``
environment variable. If it is unset (or empty) no token is ever issued or
verified — there is never a default secret. ``idempotency_key`` is generated
server-side (uuid5-style hash of user_id + tool + canonical args) so
re-proposing the same note yields the same key and cannot duplicate a write.
The client never supplies arguments or idempotency keys at confirm time.

Pure functions only: no I/O, no clock reads except the injectable ``now``.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

ENV_VAR = "AGENT_CONFIRM_SECRET"
TOKEN_VERSION = 1
DEFAULT_TTL_SECONDS = 600  # 10 minutes

# Namespace for the uuid5-style idempotency key derivation.
_IDEM_NAMESPACE = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")

ERROR_EXPIRED = "expired"
ERROR_BAD_SIGNATURE = "bad_signature"
ERROR_WRONG_USER = "wrong_user"
ERROR_MALFORMED = "malformed"
ERROR_UNAVAILABLE = "unavailable"


class ConfirmationError(Exception):
    """Raised when a proposal token cannot be issued or verified.

    ``code`` is one of ``expired``, ``bad_signature``, ``wrong_user``,
    ``malformed``, ``unavailable`` — safe to surface to the caller; it never
    contains secret material.
    """

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ProposalPayload:
    """The verified contents of a proposal token."""

    v: int
    user_id: str
    tool: str
    args: Dict[str, Any]
    idempotency_key: str
    trace_id: str
    exp: int

    @property
    def expires_at(self) -> int:
        return self.exp


def _canonical_json(obj: Any) -> bytes:
    """Canonical JSON bytes (sorted keys, no whitespace) for signing."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _secret() -> Optional[bytes]:
    """Return the configured secret, or ``None`` when unset/empty.

    Never substitutes a default: an unset secret means proposals are not
    issued and tokens are not verified (fail closed).
    """
    value = os.environ.get(ENV_VAR, "")
    if not value:
        return None
    return value.encode("utf-8")


def derive_idempotency_key(user_id: str, tool: str, args: Dict[str, Any]) -> str:
    """Server-generated idempotency key: uuid5(user_id + tool + canonical args).

    Deterministic: re-proposing the same (user, tool, args) yields the same key,
    so an executed write cannot be duplicated.
    """
    material = "\n".join([user_id, tool, _canonical_json(args).decode("utf-8")])
    return str(uuid.uuid5(_IDEM_NAMESPACE, material))


def issue_token(
    user_id: str,
    tool: str,
    args: Dict[str, Any],
    trace_id: str,
    *,
    now: Optional[float] = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> str:
    """Issue a signed proposal token for one write tool call.

    Raises :class:`ConfirmationError` with code ``unavailable`` when no secret
    is configured (never signs with a default secret).
    """
    secret = _secret()
    if secret is None:
        raise ConfirmationError(ERROR_UNAVAILABLE)

    issued_at = time.time() if now is None else now
    payload = {
        "v": TOKEN_VERSION,
        "user_id": user_id,
        "tool": tool,
        "args": dict(args),
        "idempotency_key": derive_idempotency_key(user_id, tool, args),
        "trace_id": trace_id,
        "exp": int(issued_at) + int(ttl_seconds),
    }
    payload_bytes = _canonical_json(payload)
    signature = hmac.new(secret, payload_bytes, hashlib.sha256).digest()
    return f"{_b64url_encode(payload_bytes)}.{_b64url_encode(signature)}"


def verify_token(
    token: str,
    user_id: str,
    *,
    now: Optional[float] = None,
) -> ProposalPayload:
    """Verify a proposal token and return its payload.

    Raises :class:`ConfirmationError` with codes:
      * ``unavailable``   — no secret configured (never verifies)
      * ``malformed``     — not a well-formed token / payload
      * ``bad_signature`` — signature mismatch (tampered payload)
      * ``wrong_user``    — token issued for a different principal
      * ``expired``       — token past its ``exp``
    """
    secret = _secret()
    if secret is None:
        raise ConfirmationError(ERROR_UNAVAILABLE)

    if not isinstance(token, str) or not token:
        raise ConfirmationError(ERROR_MALFORMED)
    parts = token.split(".")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ConfirmationError(ERROR_MALFORMED)
    payload_b64, signature_b64 = parts

    try:
        payload_bytes = _b64url_decode(payload_b64)
        signature_bytes = _b64url_decode(signature_b64)
    except Exception:
        raise ConfirmationError(ERROR_MALFORMED) from None
    if not payload_bytes:
        raise ConfirmationError(ERROR_MALFORMED)

    expected = hmac.new(secret, payload_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, signature_bytes):
        raise ConfirmationError(ERROR_BAD_SIGNATURE)

    try:
        raw = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        raise ConfirmationError(ERROR_MALFORMED) from None

    payload = _parse_payload(raw)

    if payload.user_id != user_id:
        raise ConfirmationError(ERROR_WRONG_USER)

    checked_at = time.time() if now is None else now
    if int(checked_at) >= payload.exp:
        raise ConfirmationError(ERROR_EXPIRED)

    return payload


def _parse_payload(raw: Any) -> ProposalPayload:
    """Validate the decoded payload shape; raise ``malformed`` on any defect."""
    if not isinstance(raw, dict):
        raise ConfirmationError(ERROR_MALFORMED)
    try:
        v = raw["v"]
        user_id = raw["user_id"]
        tool = raw["tool"]
        args = raw["args"]
        idempotency_key = raw["idempotency_key"]
        trace_id = raw["trace_id"]
        exp = raw["exp"]
    except (KeyError, TypeError):
        raise ConfirmationError(ERROR_MALFORMED) from None

    if v != TOKEN_VERSION:
        raise ConfirmationError(ERROR_MALFORMED)
    if not isinstance(user_id, str) or not user_id:
        raise ConfirmationError(ERROR_MALFORMED)
    if not isinstance(tool, str) or not tool:
        raise ConfirmationError(ERROR_MALFORMED)
    if not isinstance(args, dict):
        raise ConfirmationError(ERROR_MALFORMED)
    if not isinstance(idempotency_key, str) or not idempotency_key:
        raise ConfirmationError(ERROR_MALFORMED)
    if not isinstance(trace_id, str):
        raise ConfirmationError(ERROR_MALFORMED)
    if isinstance(exp, bool) or not isinstance(exp, int):
        raise ConfirmationError(ERROR_MALFORMED)

    return ProposalPayload(
        v=v,
        user_id=user_id,
        tool=tool,
        args=args,
        idempotency_key=idempotency_key,
        trace_id=trace_id,
        exp=exp,
    )
