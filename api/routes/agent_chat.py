"""api/routes/agent_chat.py — POST /api/agent/chat.

LLM-orchestrated agent runtime. The endpoint calls the deterministic runtime
with the authenticated AppUser and request contract. The old keyword-based
dispatch has been removed; the model proposes one typed action per turn, the
runtime validates and executes through a closed registry.

Failure modes are distinguishable by safe reason code:
  * model_error / timeout — model unavailable
  * malformed — model returned invalid JSON or unknown action
  * write_not_authorized — request lacks write_authorization
  * role_denied — user lacks required role
  * public_demo — write attempted in demo mode
  * execution_failed — tool raised an exception
  * retrieval_unavailable — Delta/retriever unavailable

A degraded Lakebase identity may perform read-only retrieval; any write fails
fast with 503.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from api.deps import AppUser, get_current_user
from api.schemas import ChatRequest, ChatResponse, ToolCall

router = APIRouter()


def _build_runtime() -> "AgentRuntime":
    """Construct the agent runtime with default transports."""
    from agent.model_client import ModelClient
    from agent.runtime import AgentRuntime, ToolRegistry

    model_client = ModelClient()
    tool_registry = ToolRegistry()
    return AgentRuntime(model_client=model_client, tool_registry=tool_registry)


@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, user: AppUser = Depends(get_current_user)) -> ChatResponse:
    """POST /api/agent/chat — LLM-orchestrated agent endpoint.

    The model proposes typed actions; the runtime validates and executes.
    No keyword fallback; on model failure a clear error is returned.
    """
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

    return ChatResponse(
        reply=result.reply,
        tool_calls=tool_call_models,
        sources=result.sources,
        available=result.available,
        empty=not result.tool_calls,
    )