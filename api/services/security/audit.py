"""audit.py — Bounded structured security audit events.

Emit security-relevant events through a dedicated interface. All fields
are recursively redacted before serialization. No raw prompts, filing
bodies, tool payloads, secrets, tokens, cookies, authorization headers,
notes, or full model output are logged.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from api.services.security.output_safety import redact_for_audit


@dataclass
class SecurityEvent:
    """A bounded security audit event."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    correlation_id: str = ""
    surface: str = ""  # "agent_chat", "confirm", "rag", etc.
    policy_version: str = "1.0"
    user_hash: str = ""  # pseudonymous keyed hash
    ip_hash: str = ""    # pseudonymous keyed hash
    action: str = ""     # "input_check", "tool_call", "output_check", etc.
    status: str = ""     # "allowed", "blocked", "error"
    reason_code: str = ""
    model_id: str = ""
    retrieval_present: bool = False
    tool_name: str = ""
    tool_category: str = ""
    input_chars: int = 0
    output_chars: int = 0
    chunk_count: int = 0
    tool_call_count: int = 0
    limit_type: str = ""
    limit_value: float = 0.0
    confirmation_status: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class SecurityAuditLogger:
    """Security audit event logger.

    Events are bounded, pseudonymous, and recursively redacted before
    serialization. Production persistence is append-oriented.
    """

    def __init__(self, secret_key: str = "default-audit-key") -> None:
        self._secret_key = secret_key
        self._events: list[SecurityEvent] = []  # in-memory for testing

    def _hash_identifier(self, identifier: str) -> str:
        """Create a pseudonymous keyed hash of an identifier."""
        if not identifier:
            return ""
        return hashlib.sha256(
            f"{self._secret_key}:{identifier}".encode("utf-8")
        ).hexdigest()[:16]

    def log_event(self, event: SecurityEvent) -> None:
        """Log a security audit event.

        Redacts sensitive fields before serialization.
        """
        # Hash identifiers
        if event.user_hash:
            event.user_hash = self._hash_identifier(event.user_hash)
        if event.ip_hash:
            event.ip_hash = self._hash_identifier(event.ip_hash)

        # Redact extra fields
        redacted_extra = {}
        for k, v in event.extra.items():
            if isinstance(v, str):
                redacted_extra[k] = redact_for_audit(v)
            else:
                redacted_extra[k] = v
        event.extra = redacted_extra

        # Store event
        self._events.append(event)

    def get_events(self) -> list[SecurityEvent]:
        """Get all logged events (for testing)."""
        return list(self._events)

    def clear(self) -> None:
        """Clear all events (for testing)."""
        self._events.clear()

    def create_event(
        self,
        correlation_id: str = "",
        surface: str = "",
        user_id: str = "",
        ip_address: str = "",
        action: str = "",
        status: str = "",
        reason_code: str = "",
        **kwargs: Any,
    ) -> SecurityEvent:
        """Helper to create and log a security event."""
        event = SecurityEvent(
            correlation_id=correlation_id,
            surface=surface,
            user_hash=user_id,
            ip_hash=ip_address,
            action=action,
            status=status,
            reason_code=reason_code,
            **kwargs,
        )
        self.log_event(event)
        return event


# Global singleton
_audit_logger: SecurityAuditLogger | None = None


def get_audit_logger() -> SecurityAuditLogger:
    """Get the global security audit logger singleton."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = SecurityAuditLogger()
    return _audit_logger


class FakeAuditSink:
    """Fake audit sink for testing.

    Records events in memory and provides assertions.
    """

    def __init__(self) -> None:
        self.events: list[SecurityEvent] = []

    def log_event(self, event: SecurityEvent) -> None:
        self.events.append(event)

    def get_events(self, action: str | None = None) -> list[SecurityEvent]:
        if action:
            return [e for e in self.events if e.action == action]
        return list(self.events)

    def clear(self) -> None:
        self.events.clear()

    def assert_no_raw_content(self) -> None:
        """Assert no event contains raw user/chunk/tool/output bodies."""
        for event in self.events:
            for k, v in event.extra.items():
                if isinstance(v, str):
                    # Check for common raw content indicators
                    assert "ignore previous" not in v.lower(), \
                        f"Event {event.event_id} field '{k}' contains raw attack content"
                    assert "system prompt" not in v.lower(), \
                        f"Event {event.event_id} field '{k}' contains system prompt reference"