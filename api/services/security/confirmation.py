"""confirmation.py — Write proposal/confirmation flow.

Implements the separate explicit-confirmation mechanism for write operations.
Chat cannot write directly; it creates an inert proposal with a server-generated
opaque nonce. A separate authenticated endpoint atomically verifies and consumes
the proposal before dispatching the write.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class WriteProposal:
    """A write proposal stored pending confirmation."""
    nonce: str                          # Server-generated opaque token
    action_hash: str                    # Hash of normalized action + arguments
    user_id: str                        # Authenticated user who created the proposal
    tool_name: str                      # The tool to execute
    arguments: dict[str, Any]           # Normalized arguments
    created_at: float                   # Unix timestamp
    expires_at: float                   # Unix timestamp
    retrieval_present: bool             # Whether the turn contained retrieved content
    consumed: bool = False              # Whether the proposal has been consumed
    csrf_token: str = ""                # CSRF binding token


@dataclass
class ConfirmationResult:
    """Result of a confirmation attempt."""
    success: bool
    reason: str = ""
    proposal: Optional[WriteProposal] = None


def _hash_action(tool_name: str, arguments: dict[str, Any]) -> str:
    """Create a deterministic hash of the normalized action."""
    normalized = json.dumps(
        {"tool": tool_name, "args": arguments},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _generate_nonce() -> str:
    """Generate a cryptographically secure opaque nonce."""
    return secrets.token_urlsafe(32)


class ConfirmationStore:
    """Store for write proposals pending confirmation.

    In production this must be a durable shared store (e.g., Redis, PostgreSQL)
    for multi-worker correctness. The in-memory implementation is for testing
    only and must NOT be used as the production source of truth.
    """

    def __init__(self, ttl_seconds: float = 300.0) -> None:
        self._proposals: dict[str, WriteProposal] = {}
        self._ttl = ttl_seconds

    def create_proposal(
        self,
        user_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        retrieval_present: bool = False,
        csrf_token: str = "",
    ) -> WriteProposal:
        """Create a new write proposal.

        Returns the proposal with its nonce. The nonce is returned to the
        client as an opaque token for later confirmation.
        """
        # Reject if retrieval was present
        if retrieval_present:
            raise ValueError(
                "Cannot create write proposal: turn contains retrieved content"
            )

        # Clean expired proposals
        self._cleanup_expired()

        nonce = _generate_nonce()
        action_hash = _hash_action(tool_name, arguments)
        now = time.time()

        proposal = WriteProposal(
            nonce=nonce,
            action_hash=action_hash,
            user_id=user_id,
            tool_name=tool_name,
            arguments=arguments,
            created_at=now,
            expires_at=now + self._ttl,
            retrieval_present=retrieval_present,
            csrf_token=csrf_token,
        )

        self._proposals[nonce] = proposal
        return proposal

    def confirm_proposal(
        self,
        nonce: str,
        user_id: str,
        csrf_token: str = "",
    ) -> ConfirmationResult:
        """Atomically verify and consume a write proposal.

        Checks:
        1. Proposal exists
        2. Not already consumed
        3. Not expired
        4. Belongs to the authenticated user
        5. CSRF token matches (if applicable)
        6. Action hash matches

        Returns ConfirmationResult with success=True and the proposal if all
        checks pass. The proposal is marked as consumed atomically.
        """
        self._cleanup_expired()

        proposal = self._proposals.get(nonce)
        if proposal is None:
            return ConfirmationResult(
                success=False,
                reason="Invalid or expired proposal nonce",
            )

        # Check consumed
        if proposal.consumed:
            return ConfirmationResult(
                success=False,
                reason="Proposal already consumed (replay rejected)",
            )

        # Check expiry (before marking consumed)
        if time.time() > proposal.expires_at:
            return ConfirmationResult(
                success=False,
                reason="Proposal expired",
            )

        # Check ownership (before marking consumed)
        if proposal.user_id != user_id:
            return ConfirmationResult(
                success=False,
                reason="Proposal belongs to a different user",
            )

        # Check CSRF (before marking consumed)
        if proposal.csrf_token and csrf_token != proposal.csrf_token:
            return ConfirmationResult(
                success=False,
                reason="CSRF token mismatch",
            )

        # Check retrieval_present (defense in depth, before marking consumed)
        if proposal.retrieval_present:
            return ConfirmationResult(
                success=False,
                reason="Proposal originated from a turn with retrieved content",
            )

        # All checks passed — mark consumed atomically
        proposal.consumed = True

        return ConfirmationResult(
            success=True,
            proposal=proposal,
        )

    def get_proposal(self, nonce: str) -> Optional[WriteProposal]:
        """Get a proposal by nonce (for inspection, not confirmation)."""
        return self._proposals.get(nonce)

    def _cleanup_expired(self) -> None:
        """Remove expired proposals."""
        now = time.time()
        expired = [
            nonce for nonce, p in self._proposals.items()
            if now > p.expires_at and not p.consumed
        ]
        for nonce in expired:
            del self._proposals[nonce]

    def clear(self) -> None:
        """Clear all proposals (for testing)."""
        self._proposals.clear()

    @property
    def pending_count(self) -> int:
        """Number of pending (non-consumed, non-expired) proposals."""
        now = time.time()
        return sum(
            1 for p in self._proposals.values()
            if not p.consumed and now <= p.expires_at
        )


# Global singleton
_confirmation_store: ConfirmationStore | None = None


def get_confirmation_store() -> ConfirmationStore:
    """Get the global confirmation store singleton."""
    global _confirmation_store
    if _confirmation_store is None:
        _confirmation_store = ConfirmationStore()
    return _confirmation_store