"""llm_security.py — Central security facade.

Single cohesive entry point for all security operations. Wraps the
input/output/retrieval rails behind a unified interface. All security
decisions go through this facade — routes and engines never implement
their own security policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from api.services.security.input_validator import (
    InputLimits,
    ValidationResult,
    validate_history,
    validate_input,
)
from api.services.security.envelope import (
    ContentType,
    EnvelopeBlock,
    encode_block,
    encode_history,
    encode_kg_result,
    encode_sec_chunk,
    encode_tool_result,
    encode_user_text,
    build_provenance,
)
from api.services.security.tool_registry import (
    ToolCategory,
    ToolRegistry,
    get_tool_registry,
)
from api.services.security.output_safety import (
    OutputVerdict,
    sanitize_output,
    detect_secrets,
    detect_prompt_leak,
    redact_for_audit,
)
from api.services.security.audit import (
    SecurityAuditLogger,
    SecurityEvent,
    get_audit_logger,
)
from api.services.security.limits import (
    LimitVerdict,
    RateLimitConfig,
    RateLimiter,
    get_rate_limiter,
)
from api.services.security.confirmation import (
    ConfirmationResult,
    ConfirmationStore,
    WriteProposal,
    get_confirmation_store,
)


@dataclass
class SecurityCheckResult:
    """Result of a complete security check."""
    allowed: bool
    reason: str = ""
    canonical_text: str = ""
    validation: Optional[ValidationResult] = None
    limit: Optional[LimitVerdict] = None
    envelope_blocks: list[EnvelopeBlock] = None
    provenance: list[dict[str, Any]] = None

    def __post_init__(self):
        if self.envelope_blocks is None:
            self.envelope_blocks = []
        if self.provenance is None:
            self.provenance = []


class LLMSecurityFacade:
    """Central security boundary for all LLM-facing surfaces.

    Provides dependency-injectable, deterministic functions for:
    - Input validation and canonicalization
    - Untrusted envelope encoding
    - Tool call gating
    - Output sanitization and leak detection
    - Security audit logging
    - Rate limiting
    - Write proposal/confirmation
    """

    def __init__(
        self,
        tool_registry: ToolRegistry | None = None,
        rate_limiter: RateLimiter | None = None,
        audit_logger: SecurityAuditLogger | None = None,
        confirmation_store: ConfirmationStore | None = None,
        input_limits: InputLimits | None = None,
        configured_secrets: list[str] | None = None,
        canary_values: list[str] | None = None,
    ) -> None:
        self._tool_registry = tool_registry or get_tool_registry()
        self._rate_limiter = rate_limiter or get_rate_limiter()
        self._audit_logger = audit_logger or get_audit_logger()
        self._confirmation_store = confirmation_store or get_confirmation_store()
        self._input_limits = input_limits or InputLimits()
        self._configured_secrets = configured_secrets or []
        self._canary_values = canary_values or []

    @property
    def tool_registry(self) -> ToolRegistry:
        return self._tool_registry

    @property
    def rate_limiter(self) -> RateLimiter:
        return self._rate_limiter

    @property
    def audit_logger(self) -> SecurityAuditLogger:
        return self._audit_logger

    @property
    def confirmation_store(self) -> ConfirmationStore:
        return self._confirmation_store

    def check_input(
        self,
        message: str,
        user_id: str = "",
        ip_address: str = "",
        correlation_id: str = "",
    ) -> SecurityCheckResult:
        """Validate user input against all security constraints.

        Checks: canonicalization, length caps, rate limits.
        Returns SecurityCheckResult with canonical text if allowed.
        """
        # Validate input
        validation = validate_input(message, self._input_limits)
        if not validation.valid:
            self._audit_logger.create_event(
                correlation_id=correlation_id,
                surface="agent_chat",
                user_id=user_id,
                ip_address=ip_address,
                action="input_check",
                status="blocked",
                reason_code="validation_failed",
                input_chars=len(message) if message else 0,
            )
            return SecurityCheckResult(
                allowed=False,
                reason=validation.reason,
                validation=validation,
            )

        # Check rate limits
        if user_id:
            limit = self._rate_limiter.check_all(user_id, ip_address)
            if not limit.allowed:
                self._audit_logger.create_event(
                    correlation_id=correlation_id,
                    surface="agent_chat",
                    user_id=user_id,
                    ip_address=ip_address,
                    action="rate_limit",
                    status="blocked",
                    reason_code=limit.limit_type,
                    limit_type=limit.limit_type,
                )
                return SecurityCheckResult(
                    allowed=False,
                    reason=limit.reason,
                    validation=validation,
                    limit=limit,
                )

        self._audit_logger.create_event(
            correlation_id=correlation_id,
            surface="agent_chat",
            user_id=user_id,
            ip_address=ip_address,
            action="input_check",
            status="allowed",
            input_chars=validation.char_count,
        )

        return SecurityCheckResult(
            allowed=True,
            canonical_text=validation.canonical_text,
            validation=validation,
        )

    def encode_untrusted_blocks(
        self,
        user_text: str,
        history: list[dict[str, str]] | None = None,
        sec_chunks: list[dict[str, Any]] | None = None,
        kg_results: list[str] | None = None,
        tool_results: list[dict[str, Any]] | None = None,
    ) -> tuple[list[EnvelopeBlock], list[dict[str, Any]]]:
        """Encode all dynamic content as untrusted envelope blocks.

        Returns (blocks, provenance_list).
        """
        blocks: list[EnvelopeBlock] = []
        provenance: list[dict[str, Any]] = []

        # User text
        user_block = encode_user_text(user_text)
        blocks.append(user_block)
        provenance.append(build_provenance(
            ContentType.USER_TEXT, user_block.block_id, source="user"
        ))

        # History
        if history:
            hist_block = encode_history(history)
            blocks.append(hist_block)
            provenance.append(build_provenance(
                ContentType.HISTORY, hist_block.block_id, source="conversation"
            ))

        # SEC chunks
        if sec_chunks:
            for i, chunk in enumerate(sec_chunks):
                chunk_text = chunk.get("chunk_text", "")
                chunk_id = chunk.get("metadata", {}).get("chunk_id", f"chunk-{i}")
                chunk_block = encode_sec_chunk(chunk_text, str(chunk_id))
                blocks.append(chunk_block)
                provenance.append(build_provenance(
                    ContentType.SEC_CHUNK, chunk_block.block_id,
                    source=chunk.get("metadata", {}).get("source", "edgar"),
                ))

        # KG results
        if kg_results:
            for i, result in enumerate(kg_results):
                kg_block = encode_kg_result(result)
                blocks.append(kg_block)
                provenance.append(build_provenance(
                    ContentType.KG_RESULT, kg_block.block_id, source="knowledge_graph"
                ))

        # Tool results
        if tool_results:
            for i, result in enumerate(tool_results):
                tool_name = result.get("name", f"tool-{i}")
                result_text = str(result.get("result", ""))
                tool_block = encode_tool_result(result_text, tool_name)
                blocks.append(tool_block)
                provenance.append(build_provenance(
                    ContentType.TOOL_RESULT, tool_block.block_id, source=tool_name
                ))

        return blocks, provenance

    def validate_tool_call(
        self,
        name: str,
        arguments: dict[str, Any],
        turn_id: str = "default",
        retrieval_present: bool = False,
    ) -> tuple[bool, Optional[str]]:
        """Validate a proposed tool call against the registry.

        Returns (valid, error_reason).
        """
        valid, reason, _ = self._tool_registry.validate_call(
            name, arguments, turn_id, retrieval_present
        )
        return valid, reason

    def check_output(
        self,
        text: str,
        correlation_id: str = "",
        user_id: str = "",
    ) -> OutputVerdict:
        """Sanitize and check LLM output for safety issues.

        Returns OutputVerdict with sanitized text.
        """
        verdict = sanitize_output(
            text,
            configured_secrets=self._configured_secrets,
            canary_values=self._canary_values,
        )

        if not verdict.safe:
            self._audit_logger.create_event(
                correlation_id=correlation_id,
                surface="agent_chat",
                user_id=user_id,
                action="output_check",
                status="blocked",
                reason_code="leak_detected" if verdict.leak_detected else "secret_detected",
            )

        return verdict

    def create_write_proposal(
        self,
        user_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        retrieval_present: bool = False,
        csrf_token: str = "",
    ) -> WriteProposal:
        """Create a write proposal for later confirmation."""
        return self._confirmation_store.create_proposal(
            user_id=user_id,
            tool_name=tool_name,
            arguments=arguments,
            retrieval_present=retrieval_present,
            csrf_token=csrf_token,
        )

    def confirm_write(
        self,
        nonce: str,
        user_id: str,
        csrf_token: str = "",
    ) -> ConfirmationResult:
        """Confirm a write proposal."""
        result = self._confirmation_store.confirm_proposal(
            nonce=nonce,
            user_id=user_id,
            csrf_token=csrf_token,
        )

        self._audit_logger.create_event(
            surface="confirm",
            user_id=user_id,
            action="confirmation",
            status="allowed" if result.success else "blocked",
            reason_code=result.reason if not result.success else "",
            confirmation_status="confirmed" if result.success else "rejected",
        )

        return result

    def redact_for_log(self, text: str) -> str:
        """Redact sensitive content for logging."""
        return redact_for_audit(text)


# Global singleton
_facade: LLMSecurityFacade | None = None


def get_security_facade() -> LLMSecurityFacade:
    """Get the global security facade singleton."""
    global _facade
    if _facade is None:
        _facade = LLMSecurityFacade()
    return _facade