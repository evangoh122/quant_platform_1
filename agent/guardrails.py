"""
agent/guardrails.py
Deterministic risk checks for order intents.
"""
from typing import Optional, List, Tuple
from datetime import datetime, timezone, timedelta

MAX_ORDER_NOTIONAL = 25000
MAX_POSITION_NOTIONAL = 50000
STALE_SIGNAL_MINUTES = 5

def validate_order(
    symbol: str, side: str, quantity: float, price: float,
    order_type: str = "MARKET",
    signal_prediction_ts: Optional[datetime] = None,
    current_position_notional: float = 0.0,
    buying_power: float = 100000.0,
    open_orders_same_symbol_side: int = 0,
    allowed_symbols: Optional[set] = None,
    is_paper: bool = True,
) -> Tuple[bool, List[str]]:
    failures = []
    notional = price * quantity
    if allowed_symbols and symbol not in allowed_symbols:
        failures.append(f"Symbol {symbol} not in allow-list")
    if not is_paper:
        failures.append("Only paper-account trading allowed")
    if quantity <= 0:
        failures.append(f"Quantity must be positive, got {quantity}")
    if notional > MAX_ORDER_NOTIONAL:
        failures.append(f"Notional ${notional:,.0f} > max ${MAX_ORDER_NOTIONAL:,.0f}")
    if current_position_notional + notional > MAX_POSITION_NOTIONAL:
        failures.append(f"Position would exceed max ${MAX_POSITION_NOTIONAL:,.0f}")
    if notional > buying_power:
        failures.append(f"Insufficient buying power")
    if open_orders_same_symbol_side > 0:
        failures.append(f"Duplicate open {side} order for {symbol}")
    if signal_prediction_ts:
        age = datetime.now(timezone.utc) - signal_prediction_ts
        if age > timedelta(minutes=STALE_SIGNAL_MINUTES):
            failures.append(f"Signal stale ({age.total_seconds()/60:.1f}min)")
    if order_type not in ("MARKET", "LIMIT"):
        failures.append(f"Unsupported order type: {order_type}")
    return (len(failures) == 0, failures)
