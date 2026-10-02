"""agent/tools_write.py — Agent write tools (Lakebase)."""
import uuid
from typing import Optional

def add_to_watchlist(symbol: str, user_id: str = "default") -> dict:
    return {"watchlist_id": str(uuid.uuid4()), "symbol": symbol, "status": "added"}

def save_research_note(symbol: str, note_text: str, signal_id: Optional[str] = None) -> dict:
    return {"note_id": str(uuid.uuid4()), "symbol": symbol, "status": "saved"}

def create_order_intent(symbol: str, side: str, quantity: float, order_type: str = "MARKET",
                        limit_price: Optional[float] = None, signal_id: Optional[str] = None) -> dict:
    return {"order_id": str(uuid.uuid4()), "status": "PENDING_APPROVAL"}

def approve_and_place_paper_order(order_id: str) -> dict:
    return {"order_id": order_id, "status": "SUBMITTED"}

def cancel_paper_order(order_id: str) -> dict:
    return {"order_id": order_id, "status": "CANCEL_REQUESTED"}

def record_agent_action(tool_name: str, action_type: str, input_summary: str, output_summary: str, status: str = "success") -> dict:
    return {"action_id": str(uuid.uuid4()), "tool_name": tool_name, "status": status}
