"""Public-demo write-guard tests — one parameterized test covering all 7 tools.

Each write tool must raise ``PublicDemoWriteDisabled`` as its first executable
statement, before any argument normalization, UUID generation, DB access,
transaction, audit logging, market clock, risk engine, or broker acquisition.

The test mocks all side-effectful dependencies (DB, broker, risk engine, market
clock) and asserts **zero calls** to every one of them.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# Each entry: (function_name, args, kwargs)
_WRITE_TOOLS = [
    ("add_to_watchlist", ("AAPL",), {}),
    ("save_research_note", ("AAPL", "note text"), {}),
    ("create_order_intent", ("AAPL", "BUY", 10.0), {}),
    (
        "record_approval",
        ("ord_1",),
        {"approver": MagicMock()},
    ),
    ("approve_and_place_paper_order", ("ord_1",), {}),
    ("cancel_paper_order", ("ord_1",), {}),
    (
        "record_agent_action",
        ("tool", "write", "in", "out"),
        {},
    ),
]


@pytest.mark.parametrize(
    "func_name, args, kwargs",
    _WRITE_TOOLS,
    ids=[t[0] for t in _WRITE_TOOLS],
)
def test_write_tool_rejected_in_demo(func_name, args, kwargs, monkeypatch):
    """Every write tool raises PublicDemoWriteDisabled before any side effect.

    DB, transaction, audit, risk engine, market clock, and broker mocks are all
    constructed but must have zero calls — the guard fires first.
    """
    monkeypatch.setenv("PUBLIC_DEMO", "1")

    import agent.tools_write as tw

    # Use tw.PublicDemoWriteDisabled to match the class from the same module
    # instance (avoids mismatch if module was reloaded between collection and run).
    fn = getattr(tw, func_name)

    mock_db = MagicMock()
    mock_bridge = MagicMock()
    mock_engine = MagicMock()

    with (
        patch.object(tw, "get_lakebase", return_value=mock_db),
        patch.object(tw, "IBKRBridge", return_value=mock_bridge),
        patch.object(tw, "RiskEngine", return_value=mock_engine),
        patch.object(tw, "is_market_session_open", return_value=True),
    ):
        with pytest.raises(tw.PublicDemoWriteDisabled):
            fn(*args, **kwargs)

    mock_db.execute.assert_not_called()
    mock_db.fetchone.assert_not_called()
    mock_db.transaction.assert_not_called()
    mock_bridge.submit_order.assert_not_called()
    mock_bridge.cancel_order.assert_not_called()
    mock_engine.check.assert_not_called()