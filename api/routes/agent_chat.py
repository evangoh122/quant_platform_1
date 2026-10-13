"""api/routes/agent_chat.py — POST /api/agent/chat.

LLM-orchestrated agent runtime. The endpoint calls the deterministic runtime
with the authenticated AppUser and request contract. The old keyword-based
dispatch has been removed; the model proposes one typed action per turn, the
runtime validates and executes through a closed registry.

Write flow (two-step, fail-closed):
  * A write turn WITHOUT ``write_authorization`` returns a signed proposal
    (``ChatResponse.pending_action``); nothing is executed until the user
    confirms.
  * A request WITH ``confirm_token`` executes exactly the proposed write —
    the server trusts only the signed token payload (tool, args, and a
    server-generated idempotency key); the client never supplies args or keys.
    No LLM call happens on confirm.

Failure modes are distinguishable by safe reason code:
  * model_error / timeout — model unavailable
  * malformed — model returned invalid JSON or unknown action
  * write_not_authorized — write tool mismatch (or confirmation unavailable)
  * confirmation_unavailable — no AGENT_CONFIRM_SECRET configured (fail closed)
  * role_denied — user lacks required role
  * public_demo — write attempted in demo mode
  * execution_failed — tool raised an exception
  * retrieval_unavailable — Delta/retriever unavailable

A degraded Lakebase identity may perform read-only retrieval; any write fails
fast with 503.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from api.deps import AppUser, ensure_role, get_current_user
from api.schemas import ChatRequest, ChatResponse, PendingAction, ToolCall

router = APIRouter()

# Confirm-token failure codes → HTTP status + safe detail (never secret material).
_CONFIRM_ERROR_STATUS: Dict[str, int] = {
    "malformed": 400,
    "bad_signature": 400,
    "wrong_user": 403,
    "expired": 410,
    "unavailable": 503,
}
_CONFIRM_ERROR_DETAIL: Dict[str, str] = {
    "malformed": "invalid confirmation token",
    "bad_signature": "invalid confirmation token",
    "wrong_user": "confirmation token does not belong to this user",
    "expired": "confirmation token has expired",
    "unavailable": "write confirmation is not configured",
}


def _build_runtime() -> "AgentRuntime":
    """Construct the agent runtime with default transports."""
    from agent.model_client import ModelClient
    from agent.runtime import AgentRuntime, ToolRegistry

    model_client = ModelClient()
    tool_registry = ToolRegistry()
    return AgentRuntime(model_client=model_client, tool_registry=tool_registry)


def _build_tool_registry() -> "ToolRegistry":
    """Construct the closed tool registry used on the confirm path."""
    from agent.runtime import ToolRegistry

    return ToolRegistry()


def _emit_audit(entry: "AuditEntry") -> None:
    """Emit an audit record for a confirm-path step (replaceable in tests)."""
    logger.info(
        "audit trace={} step={} action={} tool={} outcome={} status={}",
        entry.trace_id, entry.step, entry.action, entry.tool,
        entry.validation_outcome, entry.result_status,
    )


def _audit(action: str, tool: str, outcome: str, status: str, trace_id: str = "") -> None:
    from agent.runtime import AuditEntry

    _emit_audit(AuditEntry(
        trace_id=trace_id, step=0, action=action, tool=tool,
        validation_outcome=outcome, result_status=status,
        endpoint="/api/agent/chat",
    ))


def _confirm_write(body: ChatRequest, user: AppUser) -> ChatResponse:
    """Execute exactly the write authorized by ``body.confirm_token``.

    Order (fail-closed): degraded → token verification → public-demo/role
    re-checks → execution. Every rejected confirm emits a ``write_rejected``
    audit entry; a successful confirm emits ``write_confirmed``. No LLM call.
    """
    from agent.confirmation import ConfirmationError, verify_token

    # 1. Degraded Lakebase: writes are impossible, fail fast.
    if user.degraded:
        _audit("write_rejected", "", "degraded", "refused")
        raise HTTPException(
            status_code=503,
            detail="Account services unavailable; write operations require Lakebase",
        )

    # 2. Verify the signed proposal for this principal only.
    try:
        payload = verify_token(body.confirm_token or "", user.user_id)
    except ConfirmationError as exc:
        _audit("write_rejected", "", exc.code, "refused")
        raise HTTPException(
            status_code=_CONFIRM_ERROR_STATUS.get(exc.code, 400),
            detail=_CONFIRM_ERROR_DETAIL.get(exc.code, "invalid confirmation token"),
        ) from None

    # 3. Re-check public-demo and role on the execute path.
    from api.demo import is_public_demo

    if is_public_demo():
        _audit("write_rejected", payload.tool, "public_demo", "refused", payload.trace_id)
        raise HTTPException(
            status_code=403,
            detail="Write operations are disabled in public demo mode.",
        )
    try:
        ensure_role(user, "trader")
    except HTTPException as exc:
        _audit("write_rejected", payload.tool, "role_denied", "refused", payload.trace_id)
        raise exc

    # 4. Execute exactly what was proposed: token args + server idempotency key.
    args: Dict[str, Any] = dict(payload.args)
    args["idempotency_key"] = payload.idempotency_key
    try:
        result = _build_tool_registry().execute(
            payload.tool, args, user_id=user.user_id,
        )
    except Exception:
        logger.exception("confirmed write failed")
        _audit("execution_failed", payload.tool, "execution_failed", "error", payload.trace_id)
        raise HTTPException(status_code=503, detail="write execution failed") from None

    _audit("write_confirmed", payload.tool, "valid", "success", payload.trace_id)

    write_result = {
        "note_id": result.get("note_id"),
        "symbol": result.get("symbol", ""),
        "status": result.get("status", ""),
        "replay": bool(result.get("replay", False)),
        "trace_id": payload.trace_id,
    }
    if result.get("watchlist_id") is not None:
        write_result["watchlist_id"] = result.get("watchlist_id")

    return ChatResponse(
        reply="Confirmed. The proposed write has been executed.",
        tool_calls=[],
        sources=[],
        available=True,
        empty=False,
        write_result=write_result,
    )


@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, user: AppUser = Depends(get_current_user)) -> ChatResponse:
    """POST /api/agent/chat — LLM-orchestrated agent endpoint.

    The model proposes typed actions; the runtime validates and executes.
    No keyword fallback; on model failure a clear error is returned. A
    request carrying ``confirm_token`` executes the proposed write directly.
    """
    if body.confirm_token is not None:
        return _confirm_write(body, user)

    # Degraded Lakebase: read-only allowed, writes fail fast
    if user.degraded and body.write_authorization is not None:
        raise HTTPException(
            status_code=503,
            detail="Account services unavailable; write operations require Lakebase",
        )

    # Build runtime (lazy — avoids import-time side effects)
    try:
        runtime = _build_runtime()
    except Exception:
        logger.exception("failed to initialize agent runtime")
        return ChatResponse(
            reply="The agent runtime is currently unavailable. Please try again later.",
            tool_calls=[],
            available=False,
            empty=True,
        )

    # Run the agent loop
    try:
        result = runtime.run(
            body.message,
            user_id=user.user_id,
            role=user.role,
            write_authorization=body.write_authorization,
        )
    except Exception:
        logger.exception("agent runtime error")
        return ChatResponse(
            reply="An unexpected error occurred while processing your request.",
            tool_calls=[],
            available=False,
            empty=True,
        )

    # Map AgentResult to ChatResponse
    tool_call_models = [
        ToolCall(
            name=tc["name"],
            arguments=tc.get("arguments", {}),
            result=tc.get("result"),
            ok=tc.get("ok", True),
        )
        for tc in result.tool_calls
    ]

    pending: Optional[PendingAction] = None
    if result.pending_action:
        pa = result.pending_action
        pending = PendingAction(
            tool=pa.get("tool", ""),
            args=pa.get("args", {}),
            token=pa.get("token", ""),
            expires_at=pa.get("expires_at", ""),
            summary=pa.get("summary", ""),
        )

    return ChatResponse(
        reply=result.reply,
        tool_calls=tool_call_models,
        sources=result.sources,
        available=result.available,
        empty=not result.tool_calls and pending is None,
        pending_action=pending,
    )
