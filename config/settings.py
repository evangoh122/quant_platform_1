"""Unified configuration for the quant platform."""
import os

CATALOG = os.getenv("CATALOG", "bootcamp_students")
SCHEMA  = os.getenv("SCHEMA", "evangoh_capstone")

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")
_edgar_email_raw = os.getenv("EDGAR_EMAIL", "")
if not _edgar_email_raw or "example" in _edgar_email_raw.lower():
    raise ValueError(
        "EDGAR_EMAIL must be set to a valid contact email. "
        "Set it from environment or Databricks secret."
    )
EDGAR_EMAIL = _edgar_email_raw

TWS_HOST      = os.getenv("TWS_HOST", "127.0.0.1")
TWS_PORT      = int(os.getenv("TWS_PORT", "7497"))
TWS_CLIENT_ID = int(os.getenv("TWS_CLIENT_ID", "1"))

MAX_ORDER_NOTIONAL    = float(os.getenv("MAX_ORDER_NOTIONAL", "25000"))
MAX_POSITION_NOTIONAL = float(os.getenv("MAX_POSITION_NOTIONAL", "50000"))
STALE_SIGNAL_MINUTES  = int(os.getenv("STALE_SIGNAL_MINUTES", "5"))

MODEL_ENDPOINT     = os.getenv("MODEL_ENDPOINT", "")
PREDICTION_HORIZON = os.getenv("PREDICTION_HORIZON", "30m")
CHAT_PROVIDER      = os.getenv("CHAT_PROVIDER", "databricks")
TICKER_YAML        = os.getenv("TICKER_YAML", "config/tickers.yaml")
