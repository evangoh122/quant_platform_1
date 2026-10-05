"""tests/agent/test_contracts.py — contract validation tests.

Tests the closed model-output contract: discriminated union, typed args,
allowlists, bounded strings, and rejection of blocked tools.
"""
from __future__ import annotations

import json

import pytest

from agent.contracts import (
    ALL_TOOLS,
    RETRIEVAL_TOOLS,
    WRITE_TOOLS,
    FinalAction,
    RefuseAction,
    RetrieveAction,
    SaveResearchNoteArgs,
    SearchSecFilingsArgs,
    WriteAction,
    export_schema,
    validate_next_action,
)


class TestRetrieveAction:
    def test_valid_get_latest_signal(self):
        raw = {"action": "retrieve", "tool": "get_latest_signal", "args": {"symbol": "NVDA"}}
        action = validate_next_action(raw)
        assert isinstance(action, RetrieveAction)
        assert action.tool == "get_latest_signal"
        assert action.args.symbol == "NVDA"

    def test_valid_search_sec_filings_with_query(self):
        raw = {
            "action": "retrieve",
            "tool": "search_sec_filings",
            "args": {"symbol": "AAPL", "query": "export controls"},
        }
        action = validate_next_action(raw)
        assert isinstance(action, RetrieveAction)
        assert action.args.query == "export controls"

    def test_symbol_normalized_uppercase(self):
        raw = {"action": "retrieve", "tool": "get_latest_signal", "args": {"symbol": "nvda"}}
        action = validate_next_action(raw)
        assert action.args.symbol == "NVDA"

    def test_reject_unknown_retrieval_tool(self):
        raw = {"action": "retrieve", "tool": "unknown_tool", "args": {"symbol": "NVDA"}}
        with pytest.raises(Exception):
            validate_next_action(raw)

    def test_reject_extra_fields(self):
        raw = {
            "action": "retrieve",
            "tool": "get_latest_signal",
            "args": {"symbol": "NVDA", "extra_field": "bad"},
        }
        with pytest.raises(Exception):
            validate_next_action(raw)


class TestWriteAction:
    def test_valid_save_research_note(self):
        raw = {
            "action": "write",
            "tool": "save_research_note",
            "args": {"symbol": "NVDA", "note": "Export control risk analysis"},
        }
        action = validate_next_action(raw)
        assert isinstance(action, WriteAction)
        assert action.tool == "save_research_note"
        assert action.args.note == "Export control risk analysis"

    def test_valid_add_to_watchlist(self):
        raw = {"action": "write", "tool": "add_to_watchlist", "args": {"symbol": "MSFT"}}
        action = validate_next_action(raw)
        assert isinstance(action, WriteAction)
        assert action.tool == "add_to_watchlist"

    def test_reject_order_tool(self):
        """Order tools must never appear in the schema."""
        raw = {
            "action": "write",
            "tool": "create_order_intent",
            "args": {"symbol": "NVDA", "side": "BUY", "quantity": 10},
        }
        with pytest.raises(Exception):
            validate_next_action(raw)

    def test_reject_private_helpers(self):
        raw = {
            "action": "write",
            "tool": "_approve_and_place_paper_order",
            "args": {"order_id": "ord_1"},
        }
        with pytest.raises(Exception):
            validate_next_action(raw)


class TestFinalAndRefuse:
    def test_valid_final(self):
        raw = {"action": "final", "reply": "NVDA faces export control risk."}
        action = validate_next_action(raw)
        assert isinstance(action, FinalAction)
        assert action.reply == "NVDA faces export control risk."

    def test_valid_refuse(self):
        raw = {"action": "refuse", "reason": "Out of scope."}
        action = validate_next_action(raw)
        assert isinstance(action, RefuseAction)
        assert action.reason == "Out of scope."

    def test_reject_empty_reply(self):
        raw = {"action": "final", "reply": ""}
        with pytest.raises(Exception):
            validate_next_action(raw)


class TestAllowlists:
    def test_retrieval_tools_exactly(self):
        assert RETRIEVAL_TOOLS == {
            "get_latest_signal",
            "get_market_features",
            "get_options_features",
            "search_sec_filings",
        }

    def test_write_tools_exactly(self):
        assert WRITE_TOOLS == {"add_to_watchlist", "save_research_note"}

    def test_order_tools_not_in_all(self):
        """Order tools must never appear in the tool allowlist."""
        blocked = {
            "create_order_intent",
            "record_approval",
            "approve_and_place_paper_order",
            "cancel_paper_order",
            "record_agent_action",
        }
        assert blocked.isdisjoint(ALL_TOOLS)


class TestSchemaExport:
    def test_export_and_check(self):
        content = export_schema()
        assert content is not None
        schema = json.loads(content)
        assert "oneOf" in schema
        assert len(schema["oneOf"]) == 4

    def test_check_matches(self):
        # First export to ensure file exists
        export_schema()
        result = export_schema(check=True)
        assert result is None  # None means match


class TestBoundedStrings:
    def test_symbol_max_length(self):
        raw = {"action": "retrieve", "tool": "get_latest_signal", "args": {"symbol": "A" * 11}}
        with pytest.raises(Exception):
            validate_next_action(raw)

    def test_note_max_length(self):
        raw = {
            "action": "write",
            "tool": "save_research_note",
            "args": {"symbol": "NVDA", "note": "x" * 4001},
        }
        with pytest.raises(Exception):
            validate_next_action(raw)

    def test_query_max_length(self):
        raw = {
            "action": "retrieve",
            "tool": "search_sec_filings",
            "args": {"symbol": "NVDA", "query": "x" * 501},
        }
        with pytest.raises(Exception):
            validate_next_action(raw)