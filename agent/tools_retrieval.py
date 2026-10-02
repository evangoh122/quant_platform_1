"""agent/tools_retrieval.py — Read-only agent tools."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db.delta_adapter import read_table, latest_signals, market_features
from typing import Optional

def get_latest_signal(symbol: str) -> dict:
    df = latest_signals(symbol, limit=1)
    rows = df.collect()
    return rows[0].asDict() if rows else {}

def get_market_features(symbol: str, start_time: str, end_time: str) -> list:
    df = market_features(symbol, start_time, end_time)
    return [r.asDict() for r in df.collect()]

def get_options_features(symbol: str, expiry: Optional[str] = None) -> list:
    f = f"symbol = \'{symbol}\'"
    if expiry: f += f" AND expiry = \'{expiry}\'"
    df = read_table("gold_options_features", filters=f)
    return [r.asDict() for r in df.collect()]

def search_sec_filings(symbol: str, query: Optional[str] = None) -> list:
    df = read_table("silver_sec_sections", filters=f"ticker = \'{symbol}\'", limit=50)
    results = [r.asDict() for r in df.collect()]
    if query:
        results = [r for r in results if query.lower() in (r.get("chunk_text","") or "").lower()]
    return results

def get_cot_positioning(mapped_asset: str) -> dict:
    df = read_table("gold_cot_features", filters=f"mapped_asset = \'{mapped_asset}\'", limit=1)
    rows = df.collect()
    return rows[0].asDict() if rows else {}

def get_portfolio_positions() -> list:
    return []  # TODO: Wire to Lakebase

def get_open_orders() -> list:
    return []  # TODO: Wire to Lakebase

def get_watchlist() -> list:
    return []  # TODO: Wire to Lakebase
