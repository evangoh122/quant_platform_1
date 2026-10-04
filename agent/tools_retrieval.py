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
from typing import Any, List, Optional

from agent.guardrails import normalize_symbol
from api.services.exceptions import EmbeddingConfigError
from db.lakebase import get_lakebase

_OPEN_ORDER_STATUSES = ("PENDING_APPROVAL", "APPROVED", "SUBMITTED", "PARTIALLY_FILLED")


def _spark():
    from api.services.hybrid_retriever import _get_spark

    return _get_spark()


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
    from api.services.hybrid_retriever import _normalize_as_of
    as_of = _normalize_as_of(as_of)

    try:
        from api.services.hybrid_retriever import HybridRetriever
        from api.services.hybrid_retriever import NoCoverageError, TickerRequiredError
        from api.services.reranker import rerank

        retriever = HybridRetriever(top_k=top_k)
        docs = retriever.retrieve_and_rerank(
            query=query or symbol,
            ticker=symbol,
            as_of=as_of,
            top_k=top_k,
        )

        return [
            {
                "chunk_id": d.metadata.get("chunk_id", ""),
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
                "rerank_score": d.metadata.get("rerank_score"),
                "retrieval_mode": d.metadata.get("retrieval_mode", "hybrid"),
                **({"_warning": d.metadata["_warning"]} if d.metadata.get("_warning") else {}),
            }
            for d in docs
        ]
    except (NoCoverageError, TickerRequiredError) as e:
        import logging
        logging.warning("SEC filing lookup: %s", e)
        if isinstance(e, NoCoverageError):
            return [{"error": "no_coverage", "ticker": symbol}]
        return [{"error": "ticker_required"}]
    except EmbeddingConfigError as e:
        import logging
        logging.error("Embedding config error: %s", e)
        if getattr(e, "user_safe", False):
            safe_msg = str(e)
        else:
            safe_msg = (
                "Embedding configuration error — check EMBEDDING_PROVIDER, "
                "HF_TOKEN, or HUGGINGFACEHUB_API_TOKEN settings."
            )
        return [{
            "error": "retrieval_unavailable",
            "reason": "embedding_config",
            "message": safe_msg,
            "ticker": symbol,
        }]
    except CorpusUnavailableError as e:
        import logging
        logging.error("SEC filing retrieval unavailable: %s", e)
        return [{
            "error": "retrieval_unavailable",
            "message": "SEC filing corpus could not be loaded. Check Delta table connectivity.",
            "ticker": symbol,
        }]
    except Exception as e:
        import logging
        logging.warning("Hybrid retriever failed (%s), falling back to substring filter", e)
        try:
            from pyspark.sql import functions as F

            df = _spark().table(_fqn("silver_sec_sections")).where(
                F.col("ticker") == symbol
            )

            # Point-in-time: exclude filings accepted after as_of
            # Compare as epoch seconds to avoid Spark session timezone ambiguity.
            if as_of is not None:
                as_of_epoch = int(as_of.timestamp())
                df = df.where(
                    F.unix_timestamp(F.col("accepted_ts")) <= F.lit(as_of_epoch)
                )

            # Push query filter into Spark so it runs before the limit
            if query:
                df = df.where(
                    F.lower(F.col("chunk_text")).contains(query.lower())
                )

            df = df.orderBy(F.col("accepted_ts").desc()).limit(50)

            results = [r.asDict() for r in df.collect()]

            # Map to the same output schema as the hybrid path
            mapped = []
            for r in results:
                mapped.append({
                    "chunk_id": r.get("chunk_id", ""),
                    "accession_number": r.get("accession_number", ""),
                    "form_type": r.get("form_type", ""),
                    "accepted_ts": r.get("accepted_ts", ""),
                    "source_url": r.get("source_url", ""),
                    "ticker": r.get("ticker", ""),
                    "section": r.get("filing_section", ""),
                    "chunk_index": r.get("chunk_index", 0),
                    "chunk_text": r.get("chunk_text", ""),
                    "retrieval_mode": "substring_fallback",
                    "_warning": "hybrid_retrieval_failed",
                })
            return mapped[:top_k]
        except Exception as fallback_err:
            logging.error("Substring fallback also failed: %s", fallback_err)
            return [{
                "error": "retrieval_unavailable",
                "message": "SEC filing corpus could not be loaded. Check Delta table connectivity.",
                "ticker": symbol,
            }]


def query_sec_facts(
    ticker: str,
    metric: str,
    period: str,
    as_of: datetime,
    *,
    graph: Any = None,
) -> dict:
    """Query the SEC knowledge graph for XBRL facts.

    Strict Pydantic input validation: rejects naive/string/integer ``as_of``,
    non-string metric/period, unknown/extra args, and injection-shaped tickers
    before any store method is called.

    Returns a JSON-safe envelope labelled ``content_type: 'untrusted_tool_data'``
    with ``results`` and provenance.  Never concatenates tool values into
    instructions or executes values.
    """
    from pydantic import BaseModel, Field, field_validator, model_validator
    from typing import Any as _Any

    class _QuerySecFactsInput(BaseModel):
        model_config = {"extra": "forbid"}

        ticker: str
        metric: str = Field(min_length=1, max_length=128)
        period: str = Field(min_length=1, max_length=32)
        as_of: datetime

        @model_validator(mode="before")
        @classmethod
        def _validate_types(cls, data: dict) -> dict:
            as_of = data.get("as_of")
            if isinstance(as_of, (int, float)):
                raise ValueError(
                    "as_of must be a timezone-aware datetime, not a number"
                )
            if isinstance(as_of, str):
                raise ValueError(
                    "as_of must be a timezone-aware datetime, not a string"
                )
            return data

        @field_validator("as_of")
        @classmethod
        def _tz_aware(cls, v: datetime) -> datetime:
            if v.tzinfo is None:
                raise ValueError(
                    "as_of must be timezone-aware UTC, not naive"
                )
            return v

        @field_validator("ticker")
        @classmethod
        def _valid_ticker(cls, v: str) -> str:
            from agent.guardrails import load_allow_list
            normalized = normalize_symbol(v)
            allow_list = load_allow_list()
            if normalized not in allow_list:
                raise ValueError(
                    f"Ticker {normalized!r} is not in the configured allow-list"
                )
            return normalized

        @field_validator("metric")
        @classmethod
        def _valid_metric(cls, v: str) -> str:
            """Metric must match a valid XBRL concept name pattern.

            Allows letters, digits, dots, underscores, hyphens — the
            characters that appear in standard XBRL concept names
            (e.g. ``us-gaap:Revenues``, ``dei:EntityRegistrantName``).
            Rejects whitespace, quotes, semicolons, and other
            injection-shaped input before it reaches the backend.
            """
            import re
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9._:\-]*", v):
                raise ValueError(
                    f"Metric {v!r} does not match the allowed XBRL concept name pattern "
                    f"(letters, digits, dot, underscore, colon, hyphen; must start with a letter)"
                )
            return v

        @field_validator("period")
        @classmethod
        def _valid_period(cls, v: str) -> str:
            """Period must match one of the accepted formats.

            Accepted formats:
            - ``YYYY`` (fiscal year)
            - ``YYYY-Qn`` (quarter)
            - ``YYYY-MM-DD`` (single date / instant)
            - ``YYYY-MM-DD..YYYY-MM-DD`` (date range)
            """
            import re
            _PERIOD_RE = re.compile(
                r"\d{4}"                                        # YYYY
                r"|\d{4}-Q[1-4]"                                # YYYY-Qn
                r"|\d{4}-\d{2}-\d{2}"                           # YYYY-MM-DD
                r"|\d{4}-\d{2}-\d{2}\.\.\d{4}-\d{2}-\d{2}"     # YYYY-MM-DD..YYYY-MM-DD
            )
            if not _PERIOD_RE.fullmatch(v):
                raise ValueError(
                    f"Period {v!r} does not match any accepted format: "
                    f"YYYY, YYYY-Qn, YYYY-MM-DD, or YYYY-MM-DD..YYYY-MM-DD"
                )
            return v

        @field_validator("metric", "period")
        @classmethod
        def _non_blank_str(cls, v: str) -> str:
            if not isinstance(v, str) or not v.strip():
                raise ValueError("must be a non-blank string")
            return v

    # Validate all inputs through strict Pydantic model
    validated = _QuerySecFactsInput(
        ticker=ticker, metric=metric, period=period, as_of=as_of,
    )

    # Get or create graph store
    if graph is None:
        from api.services.sec_knowledge_graph import SecKnowledgeGraph
        graph = _get_default_graph()

    # Execute query
    result = graph.get_fact(
        ticker=validated.ticker,
        metric=validated.metric,
        period=validated.period,
        as_of=validated.as_of,
    )

    return {
        "content_type": "untrusted_tool_data",
        "results": [result] if result else [],
        "provenance": result.get("provenance", []) if result else [],
    }


def _get_default_graph():
    """Lazy default graph store (Delta-backed in production)."""
    from api.services.sec_knowledge_graph import SecKnowledgeGraph, SparkGraphStore
    from db.delta_adapter import CATALOG, SCHEMA
    store = SparkGraphStore(CATALOG, SCHEMA)
    return SecKnowledgeGraph(store)


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
