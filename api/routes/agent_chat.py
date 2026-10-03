"""api/routes/agent_chat.py — POST /api/agent/chat.

Thin, deterministic agent runtime scaffold. It routes a free-text message to
the existing ``agent.tools_retrieval`` / ``agent.tools_write`` contracts and
returns the *visible* tool calls + evidence, so the frontend can render the
chain-of-action auditably. An LLM-orchestrated runtime can be swapped in behind
the same contract later; for now the dispatch is keyword-based and never
fabricates data — a tool that cannot run (e.g. Delta unavailable) is reported
as an explicit ``ok: false`` tool call rather than a silent skip.
"""
from __future__ import annotations

import re
from typing import List, Optional

from fastapi import APIRouter, Depends
from loguru import logger

from api.deps import AppUser, ensure_role, get_current_user
from api.schemas import ChatRequest, ChatResponse, ToolCall

router = APIRouter()

_ERR_TOOL_FAILED = "tool_failed"
_ERR_UNKNOWN_TOOL = "unknown_tool"
_GENERIC_FAILURE_MESSAGE = "The tool could not complete this request."

_SYMBOL_RE = re.compile(r"[A-Za-z][A-Za-z0-9.\-]{0,9}")

_STOPWORDS = {
    "LATEST", "SIGNAL", "SIGNALS", "FOR", "THE", "A", "AN", "OF", "TO", "ME",
    "MY", "IN", "ON", "AT", "AND", "OR", "ADD", "NOTE", "NOTES", "WATCH",
    "WATCHLIST", "SEARCH", "ABOUT", "WITH", "MARKET", "PRICE", "PRICES",
    "FEATURES", "OHLCV", "SEC", "FILING", "FILINGS", "EDGAR", "PREDICT",
    "PREDICTION", "TRADE", "TRADING", "SHOW", "GET", "LOOK", "LOOKUP",
}

_allowlist: Optional[set] = None


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


def _run_tool(name: str, arguments: dict) -> ToolCall:
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
        if name == "add_to_watchlist":
            from agent.tools_write import add_to_watchlist

            return ToolCall(name=name, arguments=arguments, result=add_to_watchlist(arguments["symbol"], arguments["user_id"]), ok=True)
        if name == "save_research_note":
            from agent.tools_write import save_research_note

            return ToolCall(name=name, arguments=arguments, result=save_research_note(arguments["symbol"], arguments["note"], arguments.get("signal_id"), arguments["user_id"]), ok=True)
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


@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, user: AppUser = Depends(get_current_user)) -> ChatResponse:
    message = body.message
    symbol = _extract_symbol(message)

    if re.search(r"\bwatchlist\b|\bwatch\b", message, re.IGNORECASE):
        if symbol:
            ensure_role(user, "trader")
            tool = _run_tool("add_to_watchlist", {"symbol": symbol, "user_id": user.user_id})
            reply = f"Added {symbol} to your watchlist." if tool.ok else f"Could not add {symbol}."
            return ChatResponse(reply=reply, tool_calls=[tool], available=True, empty=not tool.ok)

    if re.search(r"\bnote\b", message, re.IGNORECASE):
        if symbol:
            ensure_role(user, "trader")
            tool = _run_tool("save_research_note", {"symbol": symbol, "note": message, "user_id": user.user_id})
            reply = f"Saved a research note for {symbol}." if tool.ok else f"Could not save note."
            return ChatResponse(reply=reply, tool_calls=[tool], available=True, empty=not tool.ok)

    if re.search(r"\bsec\b|\bfiling\b|\bedgar\b", message, re.IGNORECASE):
        if symbol:
            tool = _run_tool("search_sec_filings", {"symbol": symbol, "query": None})
            rows = (tool.result or {}).get("rows", []) if isinstance(tool.result, dict) else []
            reply = f"Found {len(rows)} filing section(s) for {symbol}." if tool.ok else f"SEC search unavailable."
            return ChatResponse(reply=reply, tool_calls=[tool], available=True, empty=not rows)

    if re.search(r"\bsignal\b|\bpredict\b|\btrade\b", message, re.IGNORECASE):
        if symbol:
            tool = _run_tool("get_latest_signal", {"symbol": symbol})
            result = tool.result or {}
            if tool.ok and result:
                reply = f"Latest {symbol} signal: {result.get('direction', '')} ({result.get('probability')})."
            else:
                reply = f"No signal yet for {symbol} — gold_trading_signals is empty."
            return ChatResponse(reply=reply, tool_calls=[tool], available=True, empty=not bool(result))

    if re.search(r"\bmarket\b|\bprice\b|\bfeatures\b|\bohlcv\b", message, re.IGNORECASE):
        if symbol:
            tool = _run_tool("get_market_features", {"symbol": symbol})
            rows = (tool.result or {}).get("rows", []) if isinstance(tool.result, dict) else []
            reply = f"Found {len(rows)} market feature row(s) for {symbol}." if tool.ok else f"Market data unavailable."
            return ChatResponse(reply=reply, tool_calls=[tool], available=True, empty=not rows)

    return ChatResponse(
        reply=(
            "I can look up signals, market features, SEC filings, and manage your "
            "watchlist and notes. Try: 'latest signal for NVDA' or 'search SEC "
            "filings for NVDA'."
        ),
        tool_calls=[],
        available=True,
        empty=True,
    )
