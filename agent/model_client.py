"""agent/model_client.py — workspace model client via Databricks SDK.

Queries the Foundation Model serving endpoint named by ``AGENT_MODEL_ENDPOINT``
through the Databricks SDK default credential chain. No external API keys;
auth uses the already-required ``databricks-sdk``.

Design constraints:
  * Deterministic: temperature=0, bounded tokens, hard wall-clock timeout.
  * No streaming for v1.
  * Captures token counts and latency but never logs prompt text.
  * Requires one JSON object; validates directly against the closed schema.
  * Does not strip markdown, eval, repair arbitrary JSON, or fall back to
    keyword dispatch.
  * Malformed / timeout / unavailable responses fail closed with no tool
    execution.
  * Transport is injectable so every offline test uses a scripted fake.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol

from loguru import logger

_DEFAULT_ENDPOINT = "databricks-claude-sonnet-5"
_MAX_INPUT_TOKENS = 4000
_MAX_OUTPUT_TOKENS = 1024
_WALL_CLOCK_TIMEOUT_SECONDS = 30
_TEMPERATURE = 0


# ── transport protocol (injectable) ──────────────────────────────────────────
class ModelTransport(Protocol):
    """Protocol for the model transport layer.

    Implementations must return a dict with at minimum ``text`` (the model's
    raw response string). Token/latency metadata is optional.
    """

    def query(
        self,
        *,
        endpoint: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        request_id: str,
    ) -> dict[str, Any]:
        """Send messages to the model endpoint and return the response."""
        ...


# ── response metadata ────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ModelResponse:
    """Structured response from the model client."""
    text: str
    request_id: str
    endpoint: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    raw: Optional[str] = None  # raw JSON string, never logged


class ModelError(Exception):
    """Raised when the model call fails (timeout, malformed, unavailable)."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


# ── Databricks SDK transport ─────────────────────────────────────────────────
class DatabricksModelTransport:
    """Production transport using the Databricks SDK.

    Uses the default credential chain (no API keys). The endpoint name is read
    from ``AGENT_MODEL_ENDPOINT`` env var or falls back to the default.
    """

    def __init__(self, endpoint: Optional[str] = None):
        self._endpoint = endpoint or os.getenv("AGENT_MODEL_ENDPOINT", _DEFAULT_ENDPOINT)

    def query(
        self,
        *,
        endpoint: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        request_id: str,
    ) -> dict[str, Any]:
        from databricks.sdk import WorkspaceClient

        client = WorkspaceClient()
        try:
            response = client.serving_endpoints.query(
                name=endpoint,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as e:
            raise ModelError(
                "endpoint_unavailable",
                f"Model endpoint query failed: {type(e).__name__}",
            ) from e

        # Extract text from the response
        choices = getattr(response, "choices", None) or []
        if not choices:
            raise ModelError("empty_response", "Model returned no choices")

        message = getattr(choices[0], "message", None)
        if message is None:
            raise ModelError("empty_message", "Model choice has no message")

        text = getattr(message, "content", None) or ""
        if not text:
            raise ModelError("empty_text", "Model returned empty text")

        # Extract usage metadata
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", 0) or 0
        output_tokens = getattr(usage, "completion_tokens", 0) or 0

        return {
            "text": text,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }


# ── model client ─────────────────────────────────────────────────────────────
class ModelClient:
    """Workspace model client with deterministic settings and closed validation.

    The transport is injectable: pass a custom ``ModelTransport`` for offline
    tests. The default ``DatabricksModelTransport`` uses the SDK credential
    chain.
    """

    def __init__(
        self,
        *,
        transport: Optional[ModelTransport] = None,
        endpoint: Optional[str] = None,
        timeout: float = _WALL_CLOCK_TIMEOUT_SECONDS,
    ):
        self._transport = transport or DatabricksModelTransport(endpoint)
        self._endpoint = endpoint or os.getenv("AGENT_MODEL_ENDPOINT", _DEFAULT_ENDPOINT)
        self._timeout = timeout

    def query_json(
        self,
        messages: list[dict[str, str]],
        *,
        request_id: Optional[str] = None,
    ) -> ModelResponse:
        """Query the model and return a validated response.

        The model is expected to return a single JSON object. The response is
        validated directly against the closed schema. No markdown stripping,
        eval, repair, or keyword fallback.

        Raises ``ModelError`` on timeout, malformed, or unavailable responses.
        """
        rid = request_id or str(uuid.uuid4())
        start = time.monotonic()

        # Bound input token count (rough estimate: 4 chars per token)
        total_chars = sum(len(m.get("content", "")) for m in messages)
        estimated_tokens = total_chars // 4
        if estimated_tokens > _MAX_INPUT_TOKENS:
            raise ModelError(
                "input_too_large",
                f"Estimated input tokens ({estimated_tokens}) exceed limit ({_MAX_INPUT_TOKENS})",
            )

        # Call the transport with wall-clock timeout
        try:
            result = self._transport.query(
                endpoint=self._endpoint,
                messages=messages,
                temperature=_TEMPERATURE,
                max_tokens=_MAX_OUTPUT_TOKENS,
                request_id=rid,
            )
        except ModelError:
            raise
        except Exception as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.warning(
                "model call failed | rid={} | elapsed_ms={:.0f} | error={}",
                rid, elapsed_ms, type(e).__name__,
            )
            raise ModelError(
                "transport_error",
                f"Model transport failed: {type(e).__name__}",
            ) from e

        elapsed_ms = (time.monotonic() - start) * 1000

        # Check wall-clock timeout
        if elapsed_ms > self._timeout * 1000:
            logger.warning(
                "model call exceeded timeout | rid={} | elapsed_ms={:.0f} | timeout_ms={:.0f}",
                rid, elapsed_ms, self._timeout * 1000,
            )
            raise ModelError(
                "timeout",
                f"Model call exceeded {self._timeout}s timeout",
            )

        text = result.get("text", "")
        input_tokens = result.get("input_tokens", 0)
        output_tokens = result.get("output_tokens", 0)

        # Log metadata (never prompt text)
        logger.info(
            "model call | rid={} | endpoint={} | elapsed_ms={:.0f} | "
            "input_tokens={} | output_tokens={}",
            rid, self._endpoint, elapsed_ms, input_tokens, output_tokens,
        )

        return ModelResponse(
            text=text,
            request_id=rid,
            endpoint=self._endpoint,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=elapsed_ms,
            raw=None,  # never store raw response
        )

    def parse_json_response(self, response: ModelResponse) -> dict:
        """Parse the model's text response as a JSON object.

        Does NOT strip markdown fences, eval, or repair. The response must be
        a valid JSON object. Raises ``ModelError`` if parsing fails.
        """
        text = response.text.strip()

        # Try direct JSON parse
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(
                "model response is not valid JSON | rid={} | error={}",
                response.request_id, e,
            )
            raise ModelError(
                "malformed_json",
                f"Model response is not valid JSON: {e}",
            ) from e

        if not isinstance(data, dict):
            raise ModelError(
                "not_object",
                "Model response is not a JSON object",
            )

        return data