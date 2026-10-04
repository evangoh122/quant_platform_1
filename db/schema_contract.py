"""db/schema_contract.py — column contracts per warehouse table.

Each query in the codebase must only reference columns listed here.
The ``check_schema_contract.py`` script DESCRIBEs each table live and
diffs against this contract to detect drift.
"""
from __future__ import annotations

import re
from typing import Dict, FrozenSet

# ── Table → allowed columns (DESCRIBE output, 2026-10-04) ────────────────────

TABLE_COLUMNS: Dict[str, FrozenSet[str]] = {
    "gold_trading_signals": frozenset({
        "signal_id", "symbol", "prediction_ts", "horizon", "direction",
        "probability", "model_version", "feature_snapshot_id", "status",
        "processed_ts",
    }),
    "gold_ohlcv_features": frozenset({
        "symbol", "feature_ts", "information_available_ts",
        "return_1m", "return_5m", "return_15m", "return_30m",
        "rvol_5m", "rvol_15m", "rvol_30m",
        "atr_14", "momentum_5m", "momentum_15m",
        "rsi_14", "vwap_deviation", "relative_volume",
        "dist_session_high", "dist_session_low",
        "processed_ts",
    }),
    "gold_options_features": frozenset({
        "symbol", "feature_ts", "information_available_ts",
        "put_volume", "call_volume", "put_call_ratio",
        "iv_atm", "iv_25d_put", "iv_25d_call", "iv_skew",
        "iv_term_slope", "avg_spread_pct", "volume_anomaly_zscore",
        "oi_concentration", "net_delta_exposure",
        "processed_ts",
    }),
    "gold_cot_features": frozenset({
        "mapped_asset", "report_date", "information_available_ts",
        "lev_money_net", "lev_money_net_chg_1w", "lev_money_pctile_52w",
        "lev_money_zscore_52w", "asset_mgr_net", "asset_mgr_pctile_52w",
        "crowding_score", "regime_label",
        "processed_ts",
    }),
    "silver_ohlcv_day_adjusted": frozenset({
        "symbol", "event_date",
        "adj_open", "adj_high", "adj_low", "adj_close", "adj_vwap", "adj_volume",
        "return_1d", "information_available_ts",
    }),
}

# ── Columns actually used by each query function ─────────────────────────────

QUERY_COLUMNS: Dict[str, Dict[str, FrozenSet[str]]] = {
    "latest_signals": {
        "gold_trading_signals": frozenset({
            "signal_id", "symbol", "prediction_ts", "horizon", "direction",
            "probability", "model_version", "feature_snapshot_id", "status",
        }),
    },
    "market_features_daily": {
        "silver_ohlcv_day_adjusted": frozenset({
            "symbol", "event_date",
            "adj_open", "adj_high", "adj_low", "adj_close", "adj_vwap", "adj_volume",
            "return_1d",
        }),
    },
    "market_features_intraday": {
        "gold_ohlcv_features": frozenset({
            "symbol", "feature_ts",
            "return_1m", "return_5m", "return_15m", "return_30m",
            "rvol_5m", "rvol_15m", "rvol_30m",
            "atr_14", "momentum_5m", "momentum_15m",
            "rsi_14", "vwap_deviation", "relative_volume",
            "dist_session_high", "dist_session_low",
        }),
    },
    "get_options_features": {
        "gold_options_features": frozenset({
            "symbol", "feature_ts",
            "put_volume", "call_volume", "put_call_ratio",
            "iv_atm", "iv_25d_put", "iv_25d_call", "iv_skew",
            "iv_term_slope", "avg_spread_pct", "volume_anomaly_zscore",
            "oi_concentration", "net_delta_exposure",
        }),
    },
    "get_cot_positioning": {
        "gold_cot_features": frozenset({
            "mapped_asset", "report_date",
            "lev_money_net", "lev_money_net_chg_1w", "lev_money_pctile_52w",
            "lev_money_zscore_52w", "asset_mgr_net", "asset_mgr_pctile_52w",
            "crowding_score", "regime_label",
        }),
    },
}

# ── Valid COT asset classes ───────────────────────────────────────────────────

COT_ASSET_CLASSES = frozenset({
    "rate", "other", "fx", "equity_index", "crypto", "commodity",
})

# ── Ticker → asset class mapping (subset; extends via config/tickers.yaml) ───

TICKER_TO_ASSET_CLASS: Dict[str, str] = {
    # Equity index proxies
    "SPY": "equity_index", "SPX": "equity_index", "QQQ": "equity_index",
    "IWM": "equity_index", "DIA": "equity_index", "VOO": "equity_index",
    "IVV": "equity_index", "VTI": "equity_index",
    # Rate proxies
    "TLT": "rate", "IEF": "rate", "SHY": "rate", "BND": "rate",
    "AGG": "rate", "TIP": "rate", "LQD": "rate", "HYG": "rate",
    # FX proxies
    "UUP": "fx", "FXE": "fx", "FXY": "fx", "FXB": "fx",
    "EWJ": "fx", "EEM": "fx",
    # Crypto proxies
    "BITO": "crypto", "COIN": "crypto",
    # Commodity proxies
    "GLD": "commodity", "SLV": "commodity", "USO": "commodity",
    "DBA": "commodity", "DBC": "commodity", "GDX": "commodity",
}


def validate_query_columns() -> list[str]:
    """Return a list of errors if any query references columns not in the contract."""
    errors: list[str] = []
    for query_name, table_cols in QUERY_COLUMNS.items():
        for table, cols in table_cols.items():
            allowed = TABLE_COLUMNS.get(table)
            if allowed is None:
                errors.append(f"{query_name}: unknown table {table!r}")
                continue
            bad = cols - allowed
            if bad:
                errors.append(
                    f"{query_name}: references columns {bad!r} not in "
                    f"{table} contract {allowed!r}"
                )
    return errors


# ── Actual SQL query validation ──────────────────────────────────────────────

_SELECT_COL_RE = re.compile(
    r"SELECT\s+(.+?)\s+FROM\s+", re.IGNORECASE | re.DOTALL
)
_ALIAS_RE = re.compile(r"\s+AS\s+(\w+)", re.IGNORECASE)
_COLUMN_NAME_RE = re.compile(r"(\w+(?:\.\w+)?)")

# Known function/expression patterns to skip (not real column refs)
_SKIP_PATTERNS = re.compile(
    r"^(?:COUNT|SUM|AVG|MIN|MAX|COALESCE|CAST|CASE|WHEN|THEN|ELSE|END|"
    r"NULLIF|ROUND|ABS|FLOOR|CEIL|LN|EXP|POWER|SQRT|LOG|"
    r"INTERVAL|EXTRACT|DATE_TRUNC|NOW|CURRENT_TIMESTAMP)\b",
    re.IGNORECASE,
)


def _extract_source_columns(sql: str) -> set[str]:
    """Extract source column names from a SELECT statement.

    Handles aliased columns (``adj_open AS open`` → ``adj_open``).
    Skips ``*`` and function calls.  Returns the set of source column names.
    """
    m = _SELECT_COL_RE.search(sql)
    if not m:
        return set()
    select_clause = m.group(1)
    columns: set[str] = set()
    for part in select_clause.split(","):
        part = part.strip()
        if not part or part == "*":
            continue
        # Skip function calls
        if _SKIP_PATTERNS.match(part):
            continue
        # Extract the source column (before any AS alias)
        source = _ALIAS_RE.split(part)[0].strip()
        # Extract just the column name (strip table prefix if any)
        col_match = _COLUMN_NAME_RE.match(source)
        if col_match:
            col = col_match.group(1).split(".")[-1]  # strip table prefix
            columns.add(col)
    return columns


def validate_actual_queries() -> list[str]:
    """Validate that actual SQL queries in the codebase match the contract.

    Imports the canonical query builders from delta_adapter and tools_retrieval,
    builds the real SQL strings, extracts their column references, and compares
    against QUERY_COLUMNS.  No duplicated hardcoded SQL — the test guards the
    actual production queries.
    """
    errors: list[str] = []

    from db import delta_adapter
    from agent import tools_retrieval

    # Build real SQL from the canonical builders
    _CATALOG = "bootcamp_students"
    _SCHEMA = "evangoh_capstone"
    _fqn = lambda t: f"{_CATALOG}.{_SCHEMA}.{t}"

    latest_sig_sql, _ = delta_adapter._build_latest_signals_query(symbol="AAPL")
    daily_sql, _ = delta_adapter._build_market_features_daily_query("AAPL", "2025-01-01", "2025-12-31")
    intraday_sql, _ = delta_adapter._build_market_features_intraday_query("AAPL", "2025-01-01", "2025-12-31")
    opts_sql, _ = tools_retrieval._build_options_query("AAPL")
    cot_sql, _ = tools_retrieval._build_cot_query("rate")

    # Validate each query's columns against the contract
    queries = [
        ("latest_signals", "gold_trading_signals", latest_sig_sql),
        ("market_features_daily", "silver_ohlcv_day_adjusted", daily_sql),
        ("market_features_intraday", "gold_ohlcv_features", intraday_sql),
        ("get_options_features", "gold_options_features", opts_sql),
        ("get_cot_positioning", "gold_cot_features", cot_sql),
    ]

    for query_name, table, sql in queries:
        actual_cols = _extract_source_columns(sql)
        if not actual_cols:
            continue  # SELECT * — can't validate

        allowed = TABLE_COLUMNS.get(table)
        if allowed is None:
            errors.append(f"{query_name}: unknown table {table!r}")
            continue

        contract_cols = QUERY_COLUMNS.get(query_name, {}).get(table)
        if contract_cols is None:
            errors.append(f"{query_name}: missing from QUERY_COLUMNS for {table}")
            continue

        # Check that actual query columns are in the table contract
        bad = actual_cols - allowed
        if bad:
            errors.append(
                f"{query_name}: SQL references columns {bad!r} not in "
                f"{table} contract"
            )

        # Check that contract matches actual query
        if contract_cols != actual_cols:
            missing_in_contract = actual_cols - contract_cols
            extra_in_contract = contract_cols - actual_cols
            if missing_in_contract:
                errors.append(
                    f"{query_name}: SQL uses {missing_in_contract!r} but "
                    f"QUERY_COLUMNS does not list them"
                )
            if extra_in_contract:
                errors.append(
                    f"{query_name}: QUERY_COLUMNS lists {extra_in_contract!r} "
                    f"but SQL does not use them"
                )

    return errors