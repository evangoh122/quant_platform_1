"""tool_registry.py — Strict tool gate.

Server-owned registry of allow-listed tools with strict Pydantic v2 schemas.
Rejects unknown names, duplicate/extra keys, and validates all arguments
before execution.
"""
from __future__ import annotations

import json
from enum import Enum
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field, field_validator


class ToolCategory(str, Enum):
    READ = "read"
    WRITE = "write"


class ToolArgument(BaseModel):
    """Strict argument model for tool calls."""
    model_config = {"extra": "forbid"}

    symbol: str = Field(
        min_length=1,
        max_length=10,
        pattern=r"^[A-Z][A-Z0-9.\-]{0,9}$",
        description="Stock ticker symbol",
    )


class AddToWatchlistArgs(ToolArgument):
    """Arguments for add_to_watchlist."""
    pass


class SaveResearchNoteArgs(ToolArgument):
    """Arguments for save_research_note."""
    note: str = Field(min_length=1, max_length=4000)
    signal_id: Optional[str] = Field(default=None, max_length=100)


class SearchSecFilingsArgs(ToolArgument):
    """Arguments for search_sec_filings."""
    query: Optional[str] = Field(default=None, max_length=500)


class GetLatestSignalArgs(ToolArgument):
    """Arguments for get_latest_signal."""
    pass


class GetMarketFeaturesArgs(ToolArgument):
    """Arguments for get_market_features."""
    start: str = Field(default="1970-01-01T00:00:00Z", max_length=30)
    end: str = Field(default="2999-01-01T00:00:00Z", max_length=30)


class GetOptionsFeaturesArgs(ToolArgument):
    """Arguments for get_options_features."""
    pass


class QuerySecFactsArgs(ToolArgument):
    """Arguments for query_sec_facts (KG lane)."""
    query: str = Field(min_length=1, max_length=500)


class CalculateFinancialMetricArgs(BaseModel):
    """Arguments for calculate_financial_metric."""
    model_config = {"extra": "forbid"}

    metric: str = Field(
        pattern=r"^(gross_margin|operating_margin|net_margin|gross_margin_growth|"
                r"free_cash_flow|current_ratio|debt_to_equity|rd_intensity|"
                r"revenue_yoy_growth|revenue|net_income)$",
    )


class CreateFinancialChartArgs(BaseModel):
    """Arguments for create_financial_chart."""
    model_config = {"extra": "forbid"}

    metric: str = Field(
        pattern=r"^(revenue|net_income|gross_profit|operating_income|"
                r"rd_expense|gross_margin|operating_margin|net_margin)$",
    )
    chart_type: str = Field(default="line", pattern=r"^(line|bar)$")


# Maximum serialized argument/result bytes
_MAX_ARG_BYTES = 10_000
_MAX_RESULT_BYTES = 50_000

# Maximum tool calls per turn
_MAX_CALLS_PER_TURN = 10


class ToolRegistration(BaseModel):
    """A registered tool in the server-owned registry."""
    model_config = {"extra": "forbid"}

    name: str
    category: ToolCategory
    args_model: type[BaseModel]
    description: str = ""
    timeout_seconds: float = 30.0


class ToolRegistry:
    """Server-owned tool registry with strict validation.

    Only explicitly registered tools can be called. Unknown names are rejected.
    Arguments are validated against strict Pydantic v2 models with extra="forbid".
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolRegistration] = {}
        self._call_counts: dict[str, int] = {}  # per-turn call counts

    def register(self, registration: ToolRegistration) -> None:
        """Register a tool."""
        self._tools[registration.name] = registration

    def get(self, name: str) -> Optional[ToolRegistration]:
        """Get a tool registration by name."""
        return self._tools.get(name)

    def is_registered(self, name: str) -> bool:
        """Check if a tool name is registered."""
        return name in self._tools

    def is_read(self, name: str) -> bool:
        """Check if a tool is read-only."""
        tool = self._tools.get(name)
        return tool is not None and tool.category == ToolCategory.READ

    def is_write(self, name: str) -> bool:
        """Check if a tool is a write tool."""
        tool = self._tools.get(name)
        return tool is not None and tool.category == ToolCategory.WRITE

    def validate_call(
        self,
        name: str,
        arguments: dict[str, Any],
        turn_id: str = "default",
        retrieval_present: bool = False,
    ) -> tuple[bool, Optional[str], Optional[BaseModel]]:
        """Validate a proposed tool call.

        Returns (valid, error_reason, validated_args).
        If valid is False, error_reason explains why.
        If valid is True, validated_args contains the parsed arguments.
        """
        # Check tool exists
        tool = self._tools.get(name)
        if tool is None:
            return False, f"Unknown tool: '{name}'", None

        # Check per-turn call count
        count_key = f"{turn_id}:{name}"
        current = self._call_counts.get(count_key, 0)
        if current >= _MAX_CALLS_PER_TURN:
            return False, f"Tool call limit exceeded for '{name}' in this turn", None

        # Write tools blocked when retrieval is present
        if tool.category == ToolCategory.WRITE and retrieval_present:
            return False, f"Write tool '{name}' blocked: turn contains retrieved content", None

        # Check serialized argument size
        try:
            arg_bytes = len(json.dumps(arguments, default=str).encode("utf-8"))
        except Exception:
            return False, f"Arguments for '{name}' could not be serialized", None

        if arg_bytes > _MAX_ARG_BYTES:
            return False, f"Arguments for '{name}' exceed {_MAX_ARG_BYTES} byte limit", None

        # Validate arguments against strict schema
        try:
            validated = tool.args_model.model_validate(arguments)
        except Exception as e:
            return False, f"Argument validation failed for '{name}': {e}", None

        # Increment call count
        self._call_counts[count_key] = current + 1

        return True, None, validated

    def reset_turn(self, turn_id: str = "default") -> None:
        """Reset call counts for a turn."""
        keys_to_remove = [k for k in self._call_counts if k.startswith(f"{turn_id}:")]
        for k in keys_to_remove:
            del self._call_counts[k]

    def list_tools(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def get_read_tools(self) -> list[str]:
        """List read-only tools."""
        return [n for n, t in self._tools.items() if t.category == ToolCategory.READ]

    def get_write_tools(self) -> list[str]:
        """List write tools."""
        return [n for n, t in self._tools.items() if t.category == ToolCategory.WRITE]


def create_default_registry() -> ToolRegistry:
    """Create the default tool registry with all current tools."""
    registry = ToolRegistry()

    # Read tools
    registry.register(ToolRegistration(
        name="get_latest_signal",
        category=ToolCategory.READ,
        args_model=GetLatestSignalArgs,
        description="Get the latest trading signal for a symbol",
    ))
    registry.register(ToolRegistration(
        name="get_market_features",
        category=ToolCategory.READ,
        args_model=GetMarketFeaturesArgs,
        description="Get market features/OHLCV data for a symbol",
    ))
    registry.register(ToolRegistration(
        name="get_options_features",
        category=ToolCategory.READ,
        args_model=GetOptionsFeaturesArgs,
        description="Get options features for a symbol",
    ))
    registry.register(ToolRegistration(
        name="search_sec_filings",
        category=ToolCategory.READ,
        args_model=SearchSecFilingsArgs,
        description="Search SEC filings for a symbol",
    ))
    registry.register(ToolRegistration(
        name="query_sec_facts",
        category=ToolCategory.READ,
        args_model=QuerySecFactsArgs,
        description="Query SEC facts from the knowledge graph",
    ))
    registry.register(ToolRegistration(
        name="calculate_financial_metric",
        category=ToolCategory.READ,
        args_model=CalculateFinancialMetricArgs,
        description="Calculate a financial metric from XBRL data",
    ))
    registry.register(ToolRegistration(
        name="create_financial_chart",
        category=ToolCategory.READ,
        args_model=CreateFinancialChartArgs,
        description="Create a chart of a financial metric's history",
    ))

    # Write tools
    registry.register(ToolRegistration(
        name="add_to_watchlist",
        category=ToolCategory.WRITE,
        args_model=AddToWatchlistArgs,
        description="Add a symbol to the user's watchlist",
    ))
    registry.register(ToolRegistration(
        name="save_research_note",
        category=ToolCategory.WRITE,
        args_model=SaveResearchNoteArgs,
        description="Save a research note for a symbol",
    ))

    return registry


# Global singleton
_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    """Get the global tool registry singleton."""
    global _registry
    if _registry is None:
        _registry = create_default_registry()
    return _registry