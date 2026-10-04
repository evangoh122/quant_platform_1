"""db/schema_contract.py — column contracts per warehouse table.

Each query in the codebase must only reference columns listed here.
The ``check_schema_contract.py`` script DESCRIBEs each table live and
diffs against this contract to detect drift.
"""
from __future__ import annotations

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
    "UUP": "FX", "FXE": "fx", "FXY": "fx", "FXB": "fx",
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