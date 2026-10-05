"""agent/contracts.py — closed model-output contracts.

Strict Pydantic v2 models defining the *only* actions the workspace LLM may
propose. The deterministic runtime validates every model response against these
schemas before executing anything.

The model never receives authority to execute a tool. It proposes one typed
action per turn; the runtime validates and executes through a closed registry.

Security surface: only the tools enumerated here are reachable. Order intent,
approval, placement, cancellation, broker, audit-helper, database, SQL, private
function, URL, code, role, user ID, and arbitrary kwargs are never exposed.
"""
from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator

# ── bounded string types ──────────────────────────────────────────────────────
_SYMBOL_MAX = 10
_QUERY_MAX = 500
_NOTE_MAX = 4000
_REPLY_MAX = 4000
_REASON_MAX = 500
_EVIDENCE_ID_MAX = 64


# ── retrieval tool argument models ────────────────────────────────────────────
class GetLatestSignalArgs(BaseModel):
    """Arguments for get_latest_signal."""
    model_config = {"extra": "forbid"}

    symbol: str = Field(min_length=1, max_length=_SYMBOL_MAX)

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, v: str) -> str:
        import re
        s = v.strip().upper()
        if not re.fullmatch(r"[A-Za-z0-9.\-]{1,10}", s):
            raise ValueError("invalid symbol")
        return s


class GetMarketFeaturesArgs(BaseModel):
    """Arguments for get_market_features."""
    model_config = {"extra": "forbid"}

    symbol: str = Field(min_length=1, max_length=_SYMBOL_MAX)

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, v: str) -> str:
        import re
        s = v.strip().upper()
        if not re.fullmatch(r"[A-Za-z0-9.\-]{1,10}", s):
            raise ValueError("invalid symbol")
        return s


class GetOptionsFeaturesArgs(BaseModel):
    """Arguments for get_options_features."""
    model_config = {"extra": "forbid"}

    symbol: str = Field(min_length=1, max_length=_SYMBOL_MAX)

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, v: str) -> str:
        import re
        s = v.strip().upper()
        if not re.fullmatch(r"[A-Za-z0-9.\-]{1,10}", s):
            raise ValueError("invalid symbol")
        return s


class SearchSecFilingsArgs(BaseModel):
    """Arguments for search_sec_filings."""
    model_config = {"extra": "forbid"}

    symbol: str = Field(min_length=1, max_length=_SYMBOL_MAX)
    query: Optional[str] = Field(default=None, max_length=_QUERY_MAX)

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, v: str) -> str:
        import re
        s = v.strip().upper()
        if not re.fullmatch(r"[A-Za-z0-9.\-]{1,10}", s):
            raise ValueError("invalid symbol")
        return s


# ── write tool argument models ────────────────────────────────────────────────
class AddToWatchlistArgs(BaseModel):
    """Arguments for add_to_watchlist."""
    model_config = {"extra": "forbid"}

    symbol: str = Field(min_length=1, max_length=_SYMBOL_MAX)

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, v: str) -> str:
        import re
        s = v.strip().upper()
        if not re.fullmatch(r"[A-Za-z0-9.\-]{1,10}", s):
            raise ValueError("invalid symbol")
        return s


class SaveResearchNoteArgs(BaseModel):
    """Arguments for save_research_note.

    ``evidence_ids`` binds the note to evidence (chunk IDs) returned in the
    same trace. The runtime enforces this binding; the model cannot fabricate
    evidence IDs that were not returned by a retrieval step.
    """
    model_config = {"extra": "forbid"}

    symbol: str = Field(min_length=1, max_length=_SYMBOL_MAX)
    note: str = Field(min_length=1, max_length=_NOTE_MAX)
    evidence_ids: List[str] = Field(
        default_factory=list,
        max_length=20,
        description="Chunk IDs from retrieval results in this trace",
    )

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, v: str) -> str:
        import re
        s = v.strip().upper()
        if not re.fullmatch(r"[A-Za-z0-9.\-]{1,10}", s):
            raise ValueError("invalid symbol")
        return s

    @field_validator("evidence_ids")
    @classmethod
    def _bound_evidence_ids(cls, v: List[str]) -> List[str]:
        for eid in v:
            if len(eid) > _EVIDENCE_ID_MAX:
                raise ValueError(f"evidence_id exceeds {_EVIDENCE_ID_MAX} chars")
        return v


# ── action discriminated union ────────────────────────────────────────────────
class RetrieveAction(BaseModel):
    """The model proposes a retrieval tool call."""
    model_config = {"extra": "forbid"}

    action: Literal["retrieve"] = "retrieve"
    tool: Literal[
        "get_latest_signal",
        "get_market_features",
        "get_options_features",
        "search_sec_filings",
    ]
    args: Union[
        GetLatestSignalArgs,
        GetMarketFeaturesArgs,
        GetOptionsFeaturesArgs,
        SearchSecFilingsArgs,
    ]


class WriteAction(BaseModel):
    """The model proposes a write tool call.

    The runtime must still validate: request-scoped write authorization,
    authenticated role, public-demo guard, symbol/evidence binding, and
    idempotency key before execution.
    """
    model_config = {"extra": "forbid"}

    action: Literal["write"] = "write"
    tool: Literal["add_to_watchlist", "save_research_note"]
    args: Union[AddToWatchlistArgs, SaveResearchNoteArgs]


class FinalAction(BaseModel):
    """The model proposes a final answer to return to the user."""
    model_config = {"extra": "forbid"}

    action: Literal["final"] = "final"
    reply: str = Field(min_length=1, max_length=_REPLY_MAX)


class RefuseAction(BaseModel):
    """The model refuses the request (e.g. out-of-scope, dangerous)."""
    model_config = {"extra": "forbid"}

    action: Literal["refuse"] = "refuse"
    reason: str = Field(min_length=1, max_length=_REASON_MAX)


# The discriminated union: exactly one of these four action types.
NextAction = Annotated[
    Union[RetrieveAction, WriteAction, FinalAction, RefuseAction],
    Field(discriminator="action"),
]

# ── allowlists (single source of truth) ───────────────────────────────────────
RETRIEVAL_TOOLS: frozenset[str] = frozenset({
    "get_latest_signal",
    "get_market_features",
    "get_options_features",
    "search_sec_filings",
})

WRITE_TOOLS: frozenset[str] = frozenset({
    "add_to_watchlist",
    "save_research_note",
})

ALL_TOOLS: frozenset[str] = RETRIEVAL_TOOLS | WRITE_TOOLS

# Tools that are never exposed to the model.
_BLOCKED_TOOLS: frozenset[str] = frozenset({
    "create_order_intent",
    "record_approval",
    "approve_and_place_paper_order",
    "cancel_paper_order",
    "record_agent_action",
})


def validate_next_action(raw: dict) -> NextAction:
    """Validate a raw dict against the closed NextAction schema.

    Returns the typed action or raises ``ValidationError``. The runtime calls
    this before any tool dispatch; a malformed response fails closed with no
    tool execution.
    """
    return NextAction.model_validate(raw)


def export_schema(check: bool = False) -> Optional[str]:
    """Export the deterministic JSON Schema to agent/schemas/next_action.v1.json.

    If ``check=True``, verify the file matches and return None on success.
    """
    import json
    from pathlib import Path

    schema_path = Path(__file__).parent / "schemas" / "next_action.v1.json"
    schema = RetrieveAction.model_json_schema()
    # Build the discriminated union schema manually for clarity.
    full_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "NextAction",
        "description": "The closed model-output contract for the agent runtime.",
        "oneOf": [
            RetrieveAction.model_json_schema(),
            WriteAction.model_json_schema(),
            FinalAction.model_json_schema(),
            RefuseAction.model_json_schema(),
        ],
        "$defs": {
            "GetLatestSignalArgs": GetLatestSignalArgs.model_json_schema(),
            "GetMarketFeaturesArgs": GetMarketFeaturesArgs.model_json_schema(),
            "GetOptionsFeaturesArgs": GetOptionsFeaturesArgs.model_json_schema(),
            "SearchSecFilingsArgs": SearchSecFilingsArgs.model_json_schema(),
            "AddToWatchlistArgs": AddToWatchlistArgs.model_json_schema(),
            "SaveResearchNoteArgs": SaveResearchNoteArgs.model_json_schema(),
        },
    }
    content = json.dumps(full_schema, indent=2, sort_keys=True) + "\n"

    if check:
        existing = schema_path.read_text(encoding="utf-8") if schema_path.exists() else None
        if existing == content:
            return None
        return f"Schema mismatch: {schema_path}"

    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_text(content, encoding="utf-8", newline="\n")
    return content


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        result = export_schema(check=True)
        if result:
            print(result, file=sys.stderr)
            sys.exit(1)
        print("Schema check passed.")
    else:
        export_schema()
        print("Schema exported.")