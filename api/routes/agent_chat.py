"""api/routes/agent_chat.py — POST /api/agent/chat and POST /api/agent/chat/confirm.

Secured agent runtime. All user input passes through the security facade
(canonicalization, injection detection, rate limits). Tool calls go through
the strict tool registry. Write operations require separate confirmation
via the /confirm endpoint — chat never commits writes directly.
"""
from __future__ import annotations

import os
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger

from api.deps import AppUser, ensure_role, get_current_user
from api.schemas import (
    ChatRequest,
    ChatResponse,
    ConfirmRequest,
    ConfirmResponse,
    ToolCall,
)
from api.services.llm_security import get_security_facade
from api.services.security.tool_registry import get_tool_registry

router = APIRouter()

_ERR_TOOL_FAILED = "tool_failed"
_ERR_UNKNOWN_TOOL = "unknown_tool"
_ERR_WRITE_REQUIRES_CONFIRMATION = "write_requires_confirmation"
_GENERIC_FAILURE_MESSAGE = "The tool could not complete this request."
_GENERIC_REFUSAL = "I cannot process that request. Please rephrase your question."

_SYMBOL_RE = re.compile(r"[A-Za-z][A-Za-z0-9.\-]{0,9}")

_STOPWORDS = {
    "LATEST", "SIGNAL", "SIGNALS", "FOR", "THE", "A", "AN", "OF", "TO", "ME",
    "MY", "IN", "ON", "AT", "AND", "OR", "ADD", "NOTE", "NOTES", "WATCH",
    "WATCHLIST", "SEARCH", "ABOUT", "WITH", "MARKET", "PRICE", "PRICES",
    "FEATURES", "OHLCV", "SEC", "FILING", "FILINGS", "EDGAR", "PREDICT",
    "PREDICTION", "TRADE", "TRADING", "SHOW", "GET", "LOOK", "LOOKUP",
}

_allowlist: Optional[set] = None


def _is_public_demo_mode() -> bool:
    """Check if public-demo mode is active (chat disabled)."""
    return os.getenv("PUBLIC_DEMO_MODE", "").strip().lower() in ("1", "true", "yes")


def _load_allowlist() -> set:
    global _allowlist
    if _allowlist is None:
        try:
            from config.tickers import get_all_ticker_symbols

            _allowlist = set(get_all_ticker_symbols())
        except Exception:  # noqa: BLE001
            _allowlist = set()
    return _allowlist


def _extract_symbol(message: str) -> Optional[str]:
    tokens = [t.strip(",.!?;:'\"()[]") for t in message.upper().split()]
    allowlist = _load_allowlist()
    candidates = [t for t in tokens if _SYMBOL_RE.fullmatch(t) and t not in _STOPWORDS]
    for tok in candidates:
        if tok in allowlist:
            return tok
    return candidates[0] if candidates else None


def _run_read_tool(name: str, arguments: dict) -> ToolCall:
    """Execute a read-only tool through the registry."""
    registry = get_tool_registry()
    valid, reason, validated = registry.validate_call(name, arguments)
    if not valid:
        return ToolCall(
            name=name,
            arguments=arguments,
            result={"error": _ERR_UNKNOWN_TOOL, "message": reason or "Tool validation failed."},
            ok=False,
        )

    try:
        if name == "get_latest_signal":
            from agent.tools_retrieval import get_latest_signal
            return ToolCall(name=name, arguments=arguments, result=get_latest_signal(arguments["symbol"]), ok=True)
        if name == "get_market_features":
            from agent.tools_retrieval import get_market_features
            result = get_market_features(
                arguments["symbol"], arguments.get("start", "1970-01-01T00:00:00Z"),
                arguments.get("end", "2999-01-01T00:00:00Z"),
            )
            return ToolCall(name=name, arguments=arguments, result={"rows": result}, ok=True)
        if name == "get_options_features":
            from agent.tools_retrieval import get_options_features
            result = get_options_features(arguments["symbol"])
            return ToolCall(name=name, arguments=arguments, result={"rows": result}, ok=True)
        if name == "search_sec_filings":
            from agent.tools_retrieval import search_sec_filings
            result = search_sec_filings(arguments["symbol"], arguments.get("query"))
            return ToolCall(name=name, arguments=arguments, result={"rows": result}, ok=True)
    except Exception:  # noqa: BLE001
        logger.exception("tool %r failed", name)
        return ToolCall(
            name=name,
            arguments=arguments,
            result={"error": _ERR_TOOL_FAILED, "message": _GENERIC_FAILURE_MESSAGE},
            ok=False,
        )
    return ToolCall(
        name=name,
        arguments=arguments,
        result={"error": _ERR_UNKNOWN_TOOL, "message": "Unknown tool requested."},
        ok=False,
    )


def _get_client_ip(request: Request) -> str:
    """Extract client IP, trusting only deployment-configured proxy headers."""
    # Only trust x-forwarded-for if behind a known proxy
    trusted_proxy = os.getenv("TRUSTED_PROXY_HEADER", "")
    if trusted_proxy:
        forwarded = request.headers.get(trusted_proxy)
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    request: Request,
    user: AppUser = Depends(get_current_user),
) -> ChatResponse:
    """Process a chat message with full security controls.

    1. Input validation (canonicalization, injection detection, rate limits)
    2. Tool calls go through strict registry
    3. Write tools return proposals, never execute directly
    4. Output is sanitized before returning
    """
    # Public-demo mode: chat is disabled
    if _is_public_demo_mode():
        raise HTTPException(status_code=404, detail="Chat is not available in demo mode.")

    facade = get_security_facade()
    ip_address = _get_client_ip(request)

    # Step 1: Input validation
    check = facade.check_input(
        body.message,
        user_id=user.user_id,
        ip_address=ip_address,
    )
    if not check.allowed:
        logger.info("Chat blocked for user %s: %s", user.user_id, check.reason)
        return ChatResponse(
            reply=_GENERIC_REFUSAL,
            tool_calls=[],
            available=True,
            empty=True,
        )

    message = check.canonical_text
    symbol = _extract_symbol(message)

    # Step 2: Route to tools through the registry
    if re.search(r"\bwatchlist\b|\bwatch\b", message, re.IGNORECASE):
        if symbol:
            ensure_role(user, "trader")
            # Write tool — create proposal instead of executing
            try:
                proposal = facade.create_write_proposal(
                    user_id=user.user_id,
                    tool_name="add_to_watchlist",
                    arguments={"symbol": symbol},
                    retrieval_present=False,
                )
                return ChatResponse(
                    reply=f"To add {symbol} to your watchlist, please confirm.",
                    tool_calls=[],
                    available=True,
                    empty=False,
                    proposal_nonce=proposal.nonce,
                    requires_confirmation=True,
                )
            except Exception:
                logger.exception("Failed to create watchlist proposal")
                return ChatResponse(
                    reply=_GENERIC_FAILURE_MESSAGE,
                    tool_calls=[],
                    available=True,
                    empty=True,
                )

    if re.search(r"\bnote\b", message, re.IGNORECASE):
        if symbol:
            ensure_role(user, "trader")
            # Write tool — create proposal instead of executing
            try:
                proposal = facade.create_write_proposal(
                    user_id=user.user_id,
                    tool_name="save_research_note",
                    arguments={"symbol": symbol, "note": message},
                    retrieval_present=False,
                )
                return ChatResponse(
                    reply=f"To save a research note for {symbol}, please confirm.",
                    tool_calls=[],
                    available=True,
                    empty=False,
                    proposal_nonce=proposal.nonce,
                    requires_confirmation=True,
                )
            except Exception:
                logger.exception("Failed to create note proposal")
                return ChatResponse(
                    reply=_GENERIC_FAILURE_MESSAGE,
                    tool_calls=[],
                    available=True,
                    empty=True,
                )

    # Read tools — execute through registry
    if re.search(r"\bsec\b|\bfiling\b|\bedgar\b", message, re.IGNORECASE):
        if symbol:
            tool = _run_read_tool("search_sec_filings", {"symbol": symbol, "query": None})
            rows = (tool.result or {}).get("rows", []) if isinstance(tool.result, dict) else []
            reply = f"Found {len(rows)} filing section(s) for {symbol}." if tool.ok else "SEC search unavailable."
            # Sanitize output
            verdict = facade.check_output(reply)
            return ChatResponse(
                reply=verdict.sanitized_text,
                tool_calls=[tool],
                available=True,
                empty=not rows,
            )

    if re.search(r"\bsignal\b|\bpredict\b|\btrade\b", message, re.IGNORECASE):
        if symbol:
            tool = _run_read_tool("get_latest_signal", {"symbol": symbol})
            result = tool.result or {}
            if tool.ok and result:
                reply = f"Latest {symbol} signal: {result.get('direction', '')} ({result.get('probability')})."
            else:
                reply = f"No signal yet for {symbol} — gold_trading_signals is empty."
            verdict = facade.check_output(reply)
            return ChatResponse(
                reply=verdict.sanitized_text,
                tool_calls=[tool],
                available=True,
                empty=not bool(result),
            )

    if re.search(r"\bmarket\b|\bprice\b|\bfeatures\b|\bohlcv\b", message, re.IGNORECASE):
        if symbol:
            tool = _run_read_tool("get_market_features", {"symbol": symbol})
            rows = (tool.result or {}).get("rows", []) if isinstance(tool.result, dict) else []
            reply = f"Found {len(rows)} market feature row(s) for {symbol}." if tool.ok else "Market data unavailable."
            verdict = facade.check_output(reply)
            return ChatResponse(
                reply=verdict.sanitized_text,
                tool_calls=[tool],
                available=True,
                empty=not rows,
            )

    reply = (
        "I can look up signals, market features, SEC filings, and manage your "
        "watchlist and notes. Try: 'latest signal for NVDA' or 'search SEC "
        "filings for NVDA'."
    )
    verdict = facade.check_output(reply)
    return ChatResponse(
        reply=verdict.sanitized_text,
        tool_calls=[],
        available=True,
        empty=True,
    )


@router.post("/chat/confirm", response_model=ConfirmResponse)
def confirm_write(
    body: ConfirmRequest,
    request: Request,
    user: AppUser = Depends(get_current_user),
) -> ConfirmResponse:
    """Confirm a write proposal. Does NOT call an LLM.

    Atomically verifies: ownership, expiry, single use, action hash,
    authorization, and absence of retrieved context before dispatching.
    """
    # Public-demo mode: confirmation is disabled
    if _is_public_demo_mode():
        raise HTTPException(status_code=404, detail="Confirmation is not available in demo mode.")

    facade = get_security_facade()

    # Dev users cannot confirm writes
    if not user.authenticated:
        raise HTTPException(status_code=401, detail="authentication required")

    result = facade.confirm_write(
        nonce=body.nonce,
        user_id=user.user_id,
        csrf_token=body.csrf_token or "",
    )

    if not result.success:
        logger.info("Confirmation rejected for user %s: %s", user.user_id, result.reason)
        return ConfirmResponse(
            success=False,
            reason=result.reason,
        )

    # Dispatch the confirmed write
    proposal = result.proposal
    tool_name = proposal.tool_name
    arguments = proposal.arguments

    try:
        if tool_name == "add_to_watchlist":
            from agent.tools_write import add_to_watchlist
            add_to_watchlist(arguments["symbol"], user.user_id)
            return ConfirmResponse(
                success=True,
                result={"status": "added", "symbol": arguments["symbol"]},
            )
        elif tool_name == "save_research_note":
            from agent.tools_write import save_research_note
            save_research_note(
                arguments["symbol"],
                arguments.get("note", ""),
                arguments.get("signal_id"),
                user.user_id,
            )
            return ConfirmResponse(
                success=True,
                result={"status": "saved", "symbol": arguments["symbol"]},
            )
        else:
            return ConfirmResponse(
                success=False,
                reason=f"Unknown write tool: {tool_name}",
            )
    except Exception:
        logger.exception("Confirmed write failed for tool %r", tool_name)
        return ConfirmResponse(
            success=False,
            reason="Write operation failed. Please try again.",
        )