"""agent/tools_retrieval.py — read-only agent tools.

Read paths are split into two backends:

  * Delta (Unity Catalog) — market/feature/signal/SEC data. Queries use Spark
    column-equality predicates (``F.col(...) == value``), never f-string SQL.
  * Lakebase (Postgres) — operational state (positions, orders, watchlist).
    Queries are parameterized (``%s`` placeholders only).

Every user-supplied symbol is normalised and allow-listed via
``agent.guardrails.normalize_symbol`` before it reaches either backend, so an
injection-shaped symbol (e.g. ``'; DROP TABLE users; --``) is rejected up front
and never becomes a SQL fragment.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from agent.guardrails import normalize_symbol
from db.lakebase import get_lakebase

_OPEN_ORDER_STATUSES = ("PENDING_APPROVAL", "APPROVED", "SUBMITTED", "PARTIALLY_FILLED")


def _spark():
    from pyspark.sql import SparkSession

    return SparkSession.builder.getOrCreate()


def _fqn(table: str) -> str:
    from db.delta_adapter import CATALOG, SCHEMA

    return f"{CATALOG}.{SCHEMA}.{table}"


# ── Delta-backed reads ────────────────────────────────────────────────────────
def get_latest_signal(symbol: str) -> dict:
    symbol = normalize_symbol(symbol)
    from db.delta_adapter import latest_signals

    df = latest_signals(symbol, limit=1)
    rows = df.collect()
    return rows[0].asDict() if rows else {}


def get_market_features(symbol: str, start_time: str, end_time: str) -> list:
    symbol = normalize_symbol(symbol)
    from db.delta_adapter import market_features

    df = market_features(symbol, start_time, end_time)
    return [r.asDict() for r in df.collect()]


def get_options_features(symbol: str, expiry: Optional[str] = None) -> list:
    symbol = normalize_symbol(symbol)
    from pyspark.sql import functions as F

    df = _spark().table(_fqn("gold_options_features")).where(F.col("symbol") == symbol)
    if expiry:
        df = df.where(F.col("expiry") == expiry)
    return [r.asDict() for r in df.collect()]


def search_sec_filings(
    symbol: str,
    query: Optional[str] = None,
    as_of: Optional[datetime] = None,
    top_k: int = 5,
) -> list:
    """Search SEC filing sections using hybrid BM25 + dense retrieval with RRF.

    Returns chunk text, accession, form_type, accepted_ts, source_url, and
    fused/rerank scores for auditability.  Point-in-time: only chunks with
    ``accepted_ts <= as_of`` are eligible.

    Returns a structured ``{"error": "retrieval_unavailable", ...}`` dict (as a
    single-element list) when the corpus cannot be loaded — never an empty list
    that the agent cannot distinguish from "no matching filings".
    """
    from api.services.hybrid_retriever import CorpusUnavailableError

    symbol = normalize_symbol(symbol)
    if as_of is None:
        as_of = datetime.now(timezone.utc)

    try:
        from api.services.hybrid_retriever import HybridRetriever
        from api.services.reranker import rerank

        retriever = HybridRetriever(top_k=top_k)
        docs = retriever.retrieve(
            query=query or symbol,
            ticker=symbol,
            as_of=as_of,
            top_k=top_k,
        )

        # Apply reranker if we have a query
        if query and len(docs) > 1:
            docs = rerank(query, docs, top_k=top_k)

        return [
            {
                "chunk_text": d.page_content,
                "accession_number": d.metadata.get("accession", ""),
                "form_type": d.metadata.get("form_type", ""),
                "accepted_ts": d.metadata.get("accepted_ts", ""),
                "source_url": d.metadata.get("source_url", ""),
                "ticker": d.metadata.get("ticker", ""),
                "section": d.metadata.get("section_id", ""),
                "chunk_index": d.metadata.get("chunk_index", 0),
                "similarity": d.metadata.get("similarity"),
                "distance": d.metadata.get("distance"),
            }
            for d in docs
        ]
    except CorpusUnavailableError as e:
        import logging
        logging.error("SEC filing retrieval unavailable: %s", e)
        return [{
            "error": "retrieval_unavailable",
            "message": f"SEC filing corpus could not be loaded: {e}",
            "ticker": symbol,
        }]
    except Exception as e:
        # Graceful fallback to substring filter
        import logging
        logging.warning("Hybrid retriever failed (%s), falling back to substring filter", e)
        from pyspark.sql import functions as F

        df = _spark().table(_fqn("silver_sec_sections")).where(
            F.col("ticker") == symbol
        ).limit(50)
        results = [r.asDict() for r in df.collect()]
        if query:
            results = [
                r for r in results
                if query.lower() in (r.get("chunk_text", "") or "").lower()
            ]
        return results[:top_k]


def get_cot_positioning(mapped_asset: str) -> dict:
    mapped_asset = normalize_symbol(mapped_asset)
    from pyspark.sql import functions as F

    df = _spark().table(_fqn("gold_cot_features")).where(
        F.col("mapped_asset") == mapped_asset
    ).limit(1)
    rows = df.collect()
    return rows[0].asDict() if rows else {}


# ── Lakebase-backed reads ─────────────────────────────────────────────────────
def get_portfolio_positions(account_id: str = "default", *, db=None) -> list:
    """Positions from Lakebase, parameterized. No f-string SQL."""
    db = db or get_lakebase()
    rows = db.execute(
        """
        SELECT account_id, symbol, quantity, avg_cost, market_price,
               realized_pnl, unrealized_pnl, updated_at
        FROM positions WHERE account_id = %s
        ORDER BY symbol
        """,
        (account_id,),
    )
    keys = [
        "account_id", "symbol", "quantity", "avg_cost", "market_price",
        "realized_pnl", "unrealized_pnl", "updated_at",
    ]
    return [dict(zip(keys, r)) for r in rows]


def get_open_orders(user_id: str = "default", *, db=None) -> list:
    """Open (non-terminal) orders from Lakebase, parameterized."""
    db = db or get_lakebase()
    rows = db.execute(
        """
        SELECT order_id, symbol, side, quantity, notional, order_type,
               limit_price, status, idempotency_key, created_at
        FROM orders
        WHERE user_id = %s AND status = ANY(%s)
        ORDER BY created_at DESC
        """,
        (user_id, list(_OPEN_ORDER_STATUSES)),
    )
    keys = [
        "order_id", "symbol", "side", "quantity", "notional", "order_type",
        "limit_price", "status", "idempotency_key", "created_at",
    ]
    return [dict(zip(keys, r)) for r in rows]


def get_watchlist(user_id: str = "default", *, db=None) -> list:
    """Watchlist entries from Lakebase, parameterized."""
    db = db or get_lakebase()
    rows = db.execute(
        """
        SELECT symbol, created_at
        FROM watchlists
        WHERE user_id = %s
        ORDER BY created_at DESC
        """,
        (user_id,),
    )
    return [{"symbol": r[0], "created_at": r[1]} for r in rows]
