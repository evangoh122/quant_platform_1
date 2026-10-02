# Databricks notebook source
# /// script
# [tool.databricks.environment]
# base_environment = "databricks_ai_v5"
# environment_version = "5"
# ///
# DBTITLE 1,Unified Project Architecture
# MAGIC %md
# MAGIC # Mid-Frequency Quant Trading Platform — Unified Project Setup
# MAGIC
# MAGIC **Schema:** `bootcamp_students.evangoh_capstone`  
# MAGIC **Deployment:** Databricks App (React + Tailwind CSS + FastAPI backend)  
# MAGIC **Source repos merged:**
# MAGIC - `Rag_workbench/` — React frontend, XBRL/financial/SEC domain logic, LangGraph agent, sentiment, verification
# MAGIC - `IBKR_workbench/` — Polygon/IBKR/EDGAR/COT/yFinance extraction clients, slippage model, ticker universe
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Unified Directory Tree
# MAGIC ```
# MAGIC quant_platform/
# MAGIC ├── app.yaml                        # Databricks App manifest
# MAGIC ├── app.py                          # FastAPI backend (entry point)
# MAGIC ├── requirements.txt                # Python deps
# MAGIC │
# MAGIC ├── frontend/                       # ← FROM Rag_workbench/frontend/ (React+Vite+Tailwind)
# MAGIC │   ├── package.json                #   + react-plotly.js for IBKR chart pages
# MAGIC │   ├── vite.config.ts
# MAGIC │   ├── tailwind.config.js
# MAGIC │   └── src/
# MAGIC │       ├── pages/
# MAGIC │       │   ├── MarketDashboard.tsx  # OHLCV + signal status + freshness
# MAGIC │       │   ├── SignalExplorer.tsx   # Model scores + feature contributions
# MAGIC │       │   ├── OptionsAnalytics.tsx # Chain, IV/skew, Greeks (from IBKR Streamlit)
# MAGIC │       │   ├── SECExplorer.tsx      # Filing search, events, source links
# MAGIC │       │   ├── AgentWorkspace.tsx   # Chat + tool traces + action buttons
# MAGIC │       │   ├── OrderApproval.tsx    # Risk checks + approve/reject
# MAGIC │       │   ├── Portfolio.tsx        # IBKR paper positions, P&L
# MAGIC │       │   └── Analytics.tsx        # Model perf, agent activity, latency
# MAGIC │       ├── components/             # Shared UI components
# MAGIC │       └── App.tsx
# MAGIC │
# MAGIC ├── etl/                            # ← FROM IBKR_workbench/etl/ (extraction clients)
# MAGIC │   ├── __init__.py
# MAGIC │   ├── polygon_client.py           # Polygon.io REST client factory
# MAGIC │   ├── extract_polygon.py          # OHLCV bars → bronze_ohlcv
# MAGIC │   ├── extract_options.py          # Options quotes/trades → bronze_options_*
# MAGIC │   ├── extract_edgar.py            # SEC EDGAR filings/facts → bronze_sec_filings
# MAGIC │   ├── extract_cot.py              # CFTC COT → bronze_cot
# MAGIC │   ├── extract_stocks.py           # IBKR live stock quotes
# MAGIC │   ├── extract_yfinance.py         # yFinance bars
# MAGIC │   ├── ibkr_client.py              # IBKR TWS API wrapper
# MAGIC │   ├── slippage.py                 # Almgren-Chriss transaction cost model
# MAGIC │   └── utils.py
# MAGIC │
# MAGIC ├── services/                       # ← FROM Rag_workbench/api/services/ (domain logic)
# MAGIC │   ├── __init__.py
# MAGIC │   ├── xbrl_parser.py              # XBRL parsing
# MAGIC │   ├── xbrl_validator.py           # XBRL validation
# MAGIC │   ├── xbrl_mapper.py              # XBRL concept mapping
# MAGIC │   ├── financial_calc.py           # Financial calculations
# MAGIC │   ├── sec_client.py               # SEC API client
# MAGIC │   ├── sec_analyzer.py             # SEC filing analysis
# MAGIC │   ├── edgar_adapter.py            # EDGAR data adapter
# MAGIC │   ├── graph_rag_engine.py         # Knowledge graph RAG
# MAGIC │   ├── sentiment.py                # Financial sentiment (Loughran-McDonald)
# MAGIC │   ├── schema_validator.py         # Schema validation
# MAGIC │   ├── semantic_validator.py       # Semantic validation
# MAGIC │   ├── verifier.py                 # NLI verification
# MAGIC │   ├── confidence_scorer.py        # Confidence scoring
# MAGIC │   ├── calibration.py              # Probability calibration
# MAGIC │   ├── peer_comparison.py          # Peer analysis
# MAGIC │   ├── langgraph_engine.py         # LangGraph orchestration
# MAGIC │   └── structure_chunker.py        # Document chunking
# MAGIC │
# MAGIC ├── db/                             # Data layer adapters
# MAGIC │   ├── __init__.py
# MAGIC │   ├── delta_adapter.py            # Replaces DuckDB get_connection() → Spark SQL
# MAGIC │   └── lakebase_client.py          # Lakebase CRUD operations
# MAGIC │
# MAGIC ├── agent/                          # AI Agent
# MAGIC │   ├── __init__.py
# MAGIC │   ├── tools_retrieval.py          # Read-only tools (get_signal, search_sec, etc.)
# MAGIC │   ├── tools_write.py              # Write tools (watchlist, orders, notes)
# MAGIC │   ├── guardrails.py               # Deterministic risk checks
# MAGIC │   └── orchestrator.py             # LangGraph agent orchestrator
# MAGIC │
# MAGIC ├── execution/                      # IBKR paper trading bridge
# MAGIC │   ├── __init__.py
# MAGIC │   ├── bridge.py                   # Isolated IBKR order submission
# MAGIC │   └── reconciliation.py           # Position/order sync
# MAGIC │
# MAGIC ├── config/                         # ← FROM IBKR_workbench/config/
# MAGIC │   ├── __init__.py
# MAGIC │   ├── tickers.py                  # Ticker universe loader
# MAGIC │   ├── tickers.yaml                # 11k+ US equities
# MAGIC │   ├── update_tickers.py           # Finviz scraper
# MAGIC │   └── settings.py                 # Unified app config
# MAGIC │
# MAGIC ├── ontology/                       # Business context & data dictionary
# MAGIC │   ├── business_terms.yaml         # Domain terminology
# MAGIC │   ├── metric_definitions.yaml     # How metrics are calculated
# MAGIC │   ├── join_hints.yaml             # Table join patterns
# MAGIC │   ├── table_semantics.yaml        # Column meanings & encodings
# MAGIC │   └── filters.yaml                # Session rules, stale thresholds
# MAGIC │
# MAGIC ├── pipelines/                      # Spark transformation notebooks
# MAGIC │   ├── bronze_to_silver.py         # Bronze → Silver transforms
# MAGIC │   ├── silver_to_gold.py           # Silver → Gold feature computation
# MAGIC │   ├── pit_feature_join.py         # Point-in-time feature assembly
# MAGIC │   └── cdf_analytics.py            # Lakebase CDF → analytics tables
# MAGIC │
# MAGIC ├── ml/                             # Model training & evaluation
# MAGIC │   ├── train_baseline.py           # Logistic regression
# MAGIC │   ├── train_challenger.py         # XGBoost/LightGBM
# MAGIC │   ├── ablation.py                 # A/B/C/D feature set comparison
# MAGIC │   ├── walk_forward.py             # Time-series validation
# MAGIC │   └── evaluation.py               # Metrics & MLflow logging
# MAGIC │
# MAGIC ├── tests/                          # ← FROM IBKR_workbench/tests/ (adapt for Delta)
# MAGIC │   ├── bronze/
# MAGIC │   ├── silver/
# MAGIC │   └── gold/
# MAGIC │
# MAGIC └── docs/
# MAGIC     └── architecture.md
# MAGIC ```

# COMMAND ----------

# DBTITLE 1,Component Mapping: Source Repos → Unified Platform
# MAGIC %md
# MAGIC ## Component Reuse Map
# MAGIC
# MAGIC ### From IBKR Workbench → `etl/` + `config/`
# MAGIC | Source File | Target | Rewiring Needed |
# MAGIC |---|---|---|
# MAGIC | `etl/polygon_client.py` | `etl/polygon_client.py` | None — pure API factory |
# MAGIC | `etl/extract_polygon.py` | `etl/extract_polygon.py` | Replace `get_connection()` DuckDB writes with `delta_adapter.write_bronze_ohlcv()` |
# MAGIC | `etl/extract_options.py` | `etl/extract_options.py` | Replace DuckDB → `delta_adapter.write_bronze_options_quotes/trades()` |
# MAGIC | `etl/extract_edgar.py` | `etl/extract_edgar.py` | Replace DuckDB → `delta_adapter.write_bronze_sec_filings()` |
# MAGIC | `etl/extract_cot.py` | `etl/extract_cot.py` | Replace DuckDB → `delta_adapter.write_bronze_cot()` |
# MAGIC | `etl/extract_stocks.py` | `etl/extract_stocks.py` | Replace DuckDB → Delta |
# MAGIC | `etl/extract_yfinance.py` | `etl/extract_yfinance.py` | Replace DuckDB → Delta |
# MAGIC | `etl/ibkr_client.py` | `etl/ibkr_client.py` | None — pure IBKR TWS wrapper |
# MAGIC | `etl/slippage.py` | `etl/slippage.py` | None — pure calculation, no DB dependency |
# MAGIC | `etl/utils.py` | `etl/utils.py` | None |
# MAGIC | `config/tickers.py` | `config/tickers.py` | None — reads YAML |
# MAGIC | `config/tickers.yaml` | `config/tickers.yaml` | None |
# MAGIC | `config/update_tickers.py` | `config/update_tickers.py` | None — Finviz scraper |
# MAGIC
# MAGIC ### From RAG Workbench → `services/` + `frontend/`
# MAGIC | Source File | Target | Rewiring Needed |
# MAGIC |---|---|---|
# MAGIC | `frontend/` (entire dir) | `frontend/` | Update API proxy in vite.config.ts → Databricks App backend; add react-plotly.js |
# MAGIC | `api/services/xbrl_*.py` (3 files) | `services/xbrl_*.py` | None — pure XBRL logic |
# MAGIC | `api/services/financial_calc.py` | `services/financial_calc.py` | None |
# MAGIC | `api/services/sec_client.py` | `services/sec_client.py` | None — SEC API client |
# MAGIC | `api/services/sec_analyzer.py` | `services/sec_analyzer.py` | None |
# MAGIC | `api/services/edgar_adapter.py` | `services/edgar_adapter.py` | Replace DuckDB/pgvector queries with Delta SQL |
# MAGIC | `api/services/graph_rag_engine.py` | `services/graph_rag_engine.py` | Replace DuckDB graph queries with Delta |
# MAGIC | `api/services/sentiment.py` | `services/sentiment.py` | None — pure NLP |
# MAGIC | `api/services/schema_validator.py` | `services/schema_validator.py` | None |
# MAGIC | `api/services/semantic_validator.py` | `services/semantic_validator.py` | None |
# MAGIC | `api/services/verifier.py` | `services/verifier.py` | None — NLI verification |
# MAGIC | `api/services/confidence_scorer.py` | `services/confidence_scorer.py` | None |
# MAGIC | `api/services/calibration.py` | `services/calibration.py` | None |
# MAGIC | `api/services/langgraph_engine.py` | `services/langgraph_engine.py` | Rewire tool bindings to agent/ tools |
# MAGIC | `api/services/structure_chunker.py` | `services/structure_chunker.py` | None |
# MAGIC | `api/models/` | `services/models/` | None — Pydantic models |
# MAGIC
# MAGIC ### New (built fresh for capstone)
# MAGIC | Module | Purpose |
# MAGIC |---|---|
# MAGIC | `db/delta_adapter.py` | Spark SQL writer replacing DuckDB `get_connection()` |
# MAGIC | `db/lakebase_client.py` | Lakebase CRUD for operational state |
# MAGIC | `agent/tools_retrieval.py` | 8 read-only agent tools (signal, market, SEC, COT, portfolio, watchlist, model) |
# MAGIC | `agent/tools_write.py` | 6 write tools (watchlist, note, order intent, approve, cancel, record) |
# MAGIC | `agent/guardrails.py` | Deterministic risk checks (allow-list, notional limit, buying power, stale signal) |
# MAGIC | `execution/bridge.py` | Isolated IBKR paper order submission |
# MAGIC | `pipelines/bronze_to_silver.py` | Spark streaming + batch bronze→silver transforms |
# MAGIC | `pipelines/silver_to_gold.py` | Gold feature computation with PIT joins |
# MAGIC | `pipelines/cdf_analytics.py` | Lakebase CDF → analytics Delta tables |
# MAGIC | `ml/train_*.py` | ML training notebooks |
# MAGIC | `ontology/*.yaml` | Business context, metrics, joins, table semantics, filters |

# COMMAND ----------

# DBTITLE 1,Create your secret scope + store API keys
# ── Step 1: Create your personal scope (run once) ──────────────────────────
import requests

host  = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().get()
token = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
headers = {"Authorization": f"Bearer {token}"}

scope_name = "evangoh_capstone"  # <-- your scope name

# Create scope (ignore error if already exists)
resp = requests.post(f"{host}/api/2.0/secrets/scopes/create",
    headers=headers, json={"scope": scope_name})
print(f"Create scope: {resp.status_code} — {resp.text}")

# ── Step 2: Store your Polygon API key ──────────────────────────────────────
# Replace YOUR_KEY_HERE with your actual key, then run ONCE and delete the value
resp = requests.post(f"{host}/api/2.0/secrets/put",
    headers=headers,
    json={"scope": scope_name, "key": "polygon_api_key", "string_value": "YOUR_KEY_HERE"}  # <-- ALREADY STORED, do not paste key again
)
print(f"Store polygon_api_key: {resp.status_code} — {resp.text}")

# ── Step 3: Verify it works ─────────────────────────────────────────────────
val = dbutils.secrets.get(scope=scope_name, key="polygon_api_key")
print(f"Read back: length={len(val)}, starts with={val[:4]}...")

# ── Step 4: Store Massive S3 credentials (for flat file downloads) ─────────
# Get these from massive.com → Settings → S3 Access / Flat Files
# These are DIFFERENT from the REST API key above!
for key_name, value in [
    ("massive_s3_access_key", "YOUR_S3_ACCESS_KEY_HERE"),
    ("massive_s3_secret_key", "YOUR_S3_SECRET_KEY_HERE"),
]:
    resp = requests.post(f"{host}/api/2.0/secrets/put",
        headers=headers,
        json={"scope": scope_name, "key": key_name, "string_value": value})
    print(f"Store {key_name}: {resp.status_code}")

# ── Add more secrets the same way: ──────────────────────────────────────────
# requests.post(f"{host}/api/2.0/secrets/put",
#     headers=headers,
#     json={"scope": scope_name, "key": "edgar_email", "string_value": "you@example.com"})

# COMMAND ----------

# DBTITLE 1,db/delta_adapter.py — Replaces DuckDB get_connection()
# db/delta_adapter.py
# Drop-in replacement for IBKR_workbench/db/database.py
# All ETL extraction clients call this instead of DuckDB get_connection()

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from datetime import datetime, timezone
from typing import List, Dict, Optional

CATALOG = "bootcamp_students"
SCHEMA  = "evangoh_capstone"

def _fqn(table: str) -> str:
    """Fully qualified table name."""
    return f"{CATALOG}.{SCHEMA}.{table}"

def _spark() -> SparkSession:
    return SparkSession.builder.getOrCreate()

def _now() -> datetime:
    return datetime.now(timezone.utc)

# ── Bronze Writers ────────────────────────────────────────────────────────────

def write_bronze_ohlcv(rows: List[Dict]) -> int:
    """Write OHLCV minute bars to bronze_ohlcv.
    
    Replaces: conn.execute("INSERT OR IGNORE INTO polygon_bars ...")
    Called by: etl/extract_polygon.py :: run_polygon_bars_etl()
    """
    if not rows:
        return 0
    spark = _spark()
    ingest_ts = _now()
    for r in rows:
        r["ingest_ts"] = ingest_ts
        r["source"] = r.get("source", "massive")
    df = spark.createDataFrame(rows)
    df.write.format("delta").mode("append").saveAsTable(_fqn("bronze_ohlcv"))
    return len(rows)

def write_bronze_options_quotes(rows: List[Dict]) -> int:
    """Write options minute quote snapshots to bronze_options_quotes.
    
    Replaces: conn.execute("INSERT OR IGNORE INTO polygon_option_snapshots ...")
    Called by: etl/extract_options.py
    """
    if not rows:
        return 0
    spark = _spark()
    ingest_ts = _now()
    for r in rows:
        r["ingest_ts"] = ingest_ts
        r["source"] = r.get("source", "massive")
    df = spark.createDataFrame(rows)
    df.write.format("delta").mode("append").saveAsTable(_fqn("bronze_options_quotes"))
    return len(rows)

def write_bronze_options_trades(rows: List[Dict]) -> int:
    """Write options minute trade bars to bronze_options_trades."""
    if not rows:
        return 0
    spark = _spark()
    ingest_ts = _now()
    for r in rows:
        r["ingest_ts"] = ingest_ts
        r["source"] = r.get("source", "massive")
    df = spark.createDataFrame(rows)
    df.write.format("delta").mode("append").saveAsTable(_fqn("bronze_options_trades"))
    return len(rows)

def write_bronze_sec_filings(rows: List[Dict]) -> int:
    """Write SEC EDGAR filings/sections/chunks to bronze_sec_filings.
    
    Replaces: conn.execute("INSERT OR IGNORE INTO edgar_filings ...")
    Called by: etl/extract_edgar.py :: run_edgar_filings_etl()
    """
    if not rows:
        return 0
    spark = _spark()
    ingest_ts = _now()
    for r in rows:
        r["ingest_ts"] = ingest_ts
        r["source"] = r.get("source", "sec_edgar")
    df = spark.createDataFrame(rows)
    df.write.format("delta").mode("append").saveAsTable(_fqn("bronze_sec_filings"))
    return len(rows)

def write_bronze_cot(rows: List[Dict]) -> int:
    """Write CFTC COT reports to bronze_cot.
    
    Replaces: conn.execute("INSERT OR IGNORE INTO cot_reports ...")
    Called by: etl/extract_cot.py :: run_cot_etl()
    """
    if not rows:
        return 0
    spark = _spark()
    ingest_ts = _now()
    for r in rows:
        r["ingest_ts"] = ingest_ts
        r["source"] = r.get("source", "cftc_cot")
    df = spark.createDataFrame(rows)
    df.write.format("delta").mode("append").saveAsTable(_fqn("bronze_cot"))
    return len(rows)

# ── Read Helpers (for agent tools and backend API) ───────────────────────────

def read_table(table: str, filters: Optional[str] = None, limit: int = 1000) -> DataFrame:
    """Read from any table in the schema with optional SQL WHERE clause."""
    spark = _spark()
    df = spark.table(_fqn(table))
    if filters:
        df = df.where(filters)
    return df.limit(limit)

def read_sql(query: str) -> DataFrame:
    """Execute arbitrary SQL against Unity Catalog."""
    return _spark().sql(query)

def latest_signals(symbol: Optional[str] = None, limit: int = 20) -> DataFrame:
    """Read latest trading signals for the agent and dashboard."""
    spark = _spark()
    df = spark.table(_fqn("gold_trading_signals"))
    if symbol:
        df = df.where(F.col("symbol") == symbol)
    return df.orderBy(F.col("prediction_ts").desc()).limit(limit)

def market_features(symbol: str, start_ts: str, end_ts: str) -> DataFrame:
    """Read OHLCV + options features for a symbol within a time range."""
    spark = _spark()
    ohlcv = spark.table(_fqn("gold_ohlcv_features")).where(
        (F.col("symbol") == symbol) &
        (F.col("feature_ts").between(start_ts, end_ts))
    )
    opts = spark.table(_fqn("gold_options_features")).where(
        (F.col("symbol") == symbol) &
        (F.col("feature_ts").between(start_ts, end_ts))
    )
    return ohlcv.join(opts, ["symbol", "feature_ts"], "left")

print("delta_adapter module defined — CATALOG:", CATALOG, "SCHEMA:", SCHEMA)

# COMMAND ----------

# DBTITLE 1,Ontology: Business Terms
# ontology/business_terms.yaml
# Domain terminology for the quant trading platform

business_terms_yaml = """
# ============================================================
# BUSINESS TERMS — Domain-specific terminology
# ============================================================

terms:
  mid_frequency_trading:
    definition: >-
      Trading strategy with decision horizons of ~15 minutes to several hours.
      Not high-frequency (microseconds) and not long-term (weeks/months).
      Databricks Spark micro-batch (10-15 sec) is appropriate for this cadence.
    aliases: [mid-freq, intraday, short-horizon]

  point_in_time_join:
    definition: >-
      AS-OF join where every feature's information_available_ts <= prediction_ts.
      Prevents look-ahead bias. SEC features use filing acceptance timestamp,
      COT uses CFTC release timestamp, market features use bar close time.
    aliases: [PIT join, as-of join, no-look-ahead]
    critical_rule: "NEVER join on filing_date; ALWAYS use accepted_ts or release_ts."

  information_available_ts:
    definition: >-
      Timestamp when a piece of information was actually observable in the market.
      For SEC: the EDGAR acceptance_ts (not filing_date).
      For COT: the CFTC release_ts (not report_date).
      For OHLCV: the bar close timestamp.
      Used as the join key for PIT feature assembly.
    critical_rule: "Every gold feature must carry this column."

  signal:
    definition: >-
      An ML model prediction for a specific symbol at a specific time.
      Contains: direction (UP/DOWN), probability [0,1], model_version,
      feature_snapshot_id linking back to the exact features used.
    table: gold_trading_signals
    status_values: [ACTIVE, EXPIRED, CONSUMED]

  order_intent:
    definition: >-
      A paper-trading order request created by the agent or user.
      Must pass deterministic risk checks and receive explicit human approval
      before being submitted to IBKR. Status lifecycle:
      PENDING_APPROVAL -> APPROVED -> SUBMITTED -> FILLED/REJECTED/CANCELLED.
    table: orders (Lakebase)

  execution_bridge:
    definition: >-
      Isolated service that owns the authenticated IBKR paper session.
      The browser and LLM never receive broker credentials.
      Only accepts validated, approved order intents.

  feature_snapshot_id:
    definition: >-
      Unique identifier for a row in gold_model_features.
      Links a signal back to the exact feature values used for prediction.
      Enables full lineage: signal -> features -> source data.

  stale_signal:
    definition: >-
      A signal whose prediction_ts is older than the configured freshness
      threshold (default: 5 minutes for intraday). Stale signals cannot
      be used for order intents; the risk service rejects them.

  trading_session:
    definition: >-
      US regular trading hours: 09:30-16:00 Eastern Time.
      Pre-market: 04:00-09:30 ET. After-hours: 16:00-20:00 ET.
      The is_regular_session flag in silver_ohlcv marks this.

  universe:
    definition: >-
      The configured set of 20-50 highly liquid US equities and ETFs
      (e.g. SPY, QQQ, NVDA, AAPL, MSFT, AMZN, META, AMD).
      Defined in config/tickers.yaml, loaded by config/tickers.py.

  tff_categories:
    definition: >-
      CFTC Traders in Financial Futures classification:
      Dealer/Intermediary, Asset Manager/Institutional, Leveraged Money,
      Other Reportables, Non-Reportables. Used for positioning/regime features.

  almgren_chriss:
    definition: >-
      Simplified square-root market-impact model from the slippage.py module.
      Three cost components: bid-ask spread, IBKR tiered commission, market impact.
      Returns round-trip costs in dollars and basis points of notional.
    module: etl/slippage.py
"""

print("Ontology: business_terms defined (", business_terms_yaml.count("definition:"), "terms )")

# COMMAND ----------

# DBTITLE 1,Ontology: Metric Definitions
# ontology/metric_definitions.yaml
# How every gold-layer metric is calculated

metric_definitions_yaml = """
# ============================================================
# METRIC DEFINITIONS — Exact calculation formulas
# ============================================================

metrics:
  # ── OHLCV Features (gold_ohlcv_features) ────────────────────────
  return_Nm:
    formula: "(close[t] - close[t-N]) / close[t-N]"
    variants: [return_1m, return_5m, return_15m, return_30m]
    source_table: silver_ohlcv
    note: "N refers to minutes, computed from minute-bar closes."

  rolling_realized_volatility:
    formula: "STDDEV(return_1m) OVER (ROWS BETWEEN N-1 PRECEDING AND CURRENT ROW)"
    variants: [rvol_5m, rvol_15m, rvol_30m]
    source_table: silver_ohlcv
    note: "Standard deviation of 1-min returns over rolling N-minute window."

  atr_14:
    formula: "EMA_14( MAX(high-low, ABS(high-prev_close), ABS(low-prev_close)) )"
    source_table: silver_ohlcv
    note: "14-period Average True Range using minute bars."

  rsi_14:
    formula: "100 - (100 / (1 + AVG(up_moves_14) / AVG(down_moves_14)))"
    source_table: silver_ohlcv
    range: "[0, 100]; >70 overbought, <30 oversold"

  vwap_deviation:
    formula: "(close - vwap) / vwap"
    source_table: silver_ohlcv
    note: "Positive = trading above VWAP; negative = below."

  relative_volume:
    formula: "volume / AVG(volume) OVER (ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)"
    source_table: silver_ohlcv
    note: ">1 means above-average volume; >3 is notable."

  # ── Options Features (gold_options_features) ───────────────────
  put_call_ratio:
    formula: "SUM(put_volume) / NULLIF(SUM(call_volume), 0)"
    source_table: silver_options_trades
    note: ">1 = more put activity (bearish signal); <0.7 = bullish."

  iv_atm:
    formula: "Implied volatility of the nearest-to-ATM option (|strike - spot| minimized)"
    source_table: silver_options_quotes
    note: "Extracted from option quotes using Black-Scholes inversion or provider IV."

  iv_skew:
    formula: "iv_25d_put - iv_25d_call"
    source_table: silver_options_quotes
    note: "Positive skew = downside protection demand. Typical range 0.02-0.15."

  iv_term_slope:
    formula: "IV(near_expiry_ATM) - IV(far_expiry_ATM)"
    source_table: silver_options_quotes
    note: "Positive = near-term volatility elevated (event premium)."

  volume_anomaly_zscore:
    formula: "(volume_today - AVG(volume_20d)) / STDDEV(volume_20d)"
    source_table: silver_options_trades
    note: ">2.0 is statistically unusual options activity."

  # ── SEC Features (gold_sec_features) ─────────────────────────
  sentiment_score:
    formula: "(positive_words - negative_words) / total_words"
    dictionary: "Loughran-McDonald financial sentiment lexicon"
    source_table: silver_sec_sections
    range: "[-1, +1]"

  risk_factor_change:
    formula: "1 - cosine_similarity(current_item1a_embedding, prior_item1a_embedding)"
    source_table: silver_sec_sections
    note: "Higher = more change in risk disclosures. >0.3 is material."

  filing_similarity:
    formula: "cosine_similarity(current_filing_embedding, prior_same_form_embedding)"
    source_table: silver_sec_sections
    note: "Lower = more novel content. <0.7 is noteworthy."

  # ── COT Features (gold_cot_features) ─────────────────────────
  lev_money_pctile_52w:
    formula: "PERCENT_RANK() OVER (ORDER BY lev_money_net ROWS BETWEEN 51 PRECEDING AND CURRENT ROW)"
    source_table: silver_cot_positions
    note: ">0.9 = historically extreme long positioning; <0.1 = extreme short."

  lev_money_zscore_52w:
    formula: "(lev_money_net - AVG_52w) / STDDEV_52w"
    source_table: silver_cot_positions
    note: "|z| > 2 = statistically extreme positioning."

  crowding_score:
    formula: "weighted_avg(lev_money_pctile, asset_mgr_pctile, dealer_pctile)"
    source_table: silver_cot_positions
    note: "Composite indicator; extreme crowding may precede reversals."

  # ── Model Performance Metrics ───────────────────────────────
  directional_accuracy:
    formula: "COUNT(correct_direction) / COUNT(total_predictions)"
    note: ">0.52 is edge; >0.55 is strong in liquid equities."

  information_coefficient:
    formula: "CORR(predicted_probability, realized_return)"
    note: "Rank IC typically 0.02-0.10 for viable signals."

  transaction_cost_adjusted_return:
    formula: "gross_return - (spread_cost + commission + market_impact) / notional"
    module: etl/slippage.py
    note: "Uses IBKR tiered commission schedule + Almgren-Chriss impact model."

  # ── Latency / Velocity Metrics ──────────────────────────────
  end_to_end_latency:
    formula: "signal_visible_ts - provider_event_ts"
    slo: "<60 seconds (<=50 sec typical)"
    budget:
      provider_to_ingestion: "0-10 sec"
      spark_micro_batch: "<=15 sec"
      feature_update: "<=10 sec"
      model_inference: "<=5 sec"
      persist_and_refresh: "<=10 sec"
"""

print("Ontology: metric_definitions defined (", metric_definitions_yaml.count("formula:"), "metrics )")

# COMMAND ----------

# DBTITLE 1,Ontology: Join Hints & Table Lineage
# ontology/join_hints.yaml
# How tables connect across the medallion layers

join_hints_yaml = """
# ============================================================
# JOIN HINTS — Table relationships and join patterns
# ============================================================

lineage:
  # ── Bronze → Silver ───────────────────────────────────────
  bronze_ohlcv -> silver_ohlcv:
    join_key: [symbol, event_ts]
    transform: "Schema validation, UTC normalization, session flags, dedup by hash, missing-bar detection"

  bronze_options_quotes -> silver_options_quotes:
    join_key: [option_symbol, participant_ts]
    transform: "Parse OCC symbology → underlying/expiry/strike/right, compute midpoint/spread, flag stale/locked/crossed"

  bronze_options_trades -> silver_options_trades:
    join_key: [option_symbol, participant_ts]
    transform: "Parse OCC symbology, compute notional (volume*close*100), dedup"

  bronze_sec_filings -> silver_sec_sections:
    join_key: [accession_number, chunk_id]
    transform: "HTML/XML strip, section detection, text cleaning, char count"

  bronze_sec_filings -> silver_sec_entities:
    join_key: [accession_number]
    transform: "XBRL fact extraction, event detection, entity recognition"

  bronze_cot -> silver_cot_positions:
    join_key: [report_date, market_code]
    transform: "Compute net positions (long-short), normalize to %OI, map to asset regimes"

  # ── Silver → Gold ────────────────────────────────────────
  silver_ohlcv -> gold_ohlcv_features:
    join_key: [symbol, event_ts -> feature_ts]
    transform: "Window functions: returns, rvol, ATR, RSI, VWAP deviation, relative volume"
    pit_column: "information_available_ts = event_ts (bar close time)"

  silver_options_quotes + silver_options_trades -> gold_options_features:
    join_key: [underlying -> symbol, participant_ts -> feature_ts]
    transform: "Aggregate P/C ratio, IV surface, skew, term structure, volume anomaly"
    pit_column: "information_available_ts = MAX(participant_ts) in aggregation window"

  silver_sec_sections + silver_sec_entities -> gold_sec_features:
    join_key: [ticker, accession_number]
    transform: "Sentiment (Loughran-McDonald), risk-factor cosine distance, filing similarity, event flags"
    pit_column: "information_available_ts = accepted_ts (EDGAR acceptance, NOT filing_date)"

  silver_cot_positions -> gold_cot_features:
    join_key: [mapped_asset, report_date]
    transform: "52-week percentile, z-score, weekly change, crowding score, regime label"
    pit_column: "information_available_ts = release_ts (CFTC publication, NOT report_date)"

  # ── Gold → Model Features (PIT Assembly) ──────────────────
  gold_model_features:
    description: "Point-in-time joined feature matrix"
    assembly_rule: >
      For each (symbol, prediction_ts):
        1. OHLCV features: latest where information_available_ts <= prediction_ts
        2. Options features: latest where information_available_ts <= prediction_ts
        3. SEC features: latest where information_available_ts <= prediction_ts
        4. COT features: latest where information_available_ts <= prediction_ts
      AS-OF join semantics. Test: assert no feature has info_ts > prediction_ts.
    join_sql_pattern: |
      SELECT o.*, opt.*, sec.*, cot.*
      FROM gold_ohlcv_features o
      ASOF JOIN gold_options_features opt
        ON o.symbol = opt.symbol AND o.feature_ts >= opt.information_available_ts
      ASOF JOIN gold_sec_features sec
        ON o.symbol = sec.ticker AND o.feature_ts >= sec.information_available_ts
      ASOF JOIN gold_cot_features cot
        ON <mapped_asset_logic> AND o.feature_ts >= cot.information_available_ts

  # ── Lakebase → Analytics (CDF) ──────────────────────────
  lakebase_orders + lakebase_executions -> analytics_trading_activity:
    cdf_source: "Lakebase CDF on orders, executions, positions"
    join_key: [order_id]
    metrics: "fill rate, slippage, realized P&L, turnover"

  lakebase_agent_actions -> analytics_agent_activity:
    cdf_source: "Lakebase CDF on agent_actions"
    metrics: "tool call counts, success/failure, write-action frequency, latency"

  gold_trading_signals + realized_returns -> analytics_model_performance:
    join_key: [symbol, prediction_ts]
    metrics: "hit rate, ROC-AUC, IC, return by decile, model version comparison"
"""

print("Ontology: join_hints defined (", join_hints_yaml.count("->"), "lineage edges )")

# COMMAND ----------

# DBTITLE 1,Ontology: Table Semantics & Filters
# ontology/table_semantics.yaml + filters.yaml
# Column meanings, encodings, partition patterns, and filter rules

table_semantics_yaml = """
# ============================================================
# TABLE SEMANTICS — Column meanings, encodings, partitioning
# ============================================================

tables:
  bronze_ohlcv:
    grain: "One row per (symbol, event_ts, timespan) — one minute bar"
    partitioned_by: symbol
    dedup_strategy: "(symbol, event_ts, timespan) is the natural key; use MERGE or dedup_hash"
    columns:
      event_ts: "Bar close timestamp from Massive provider (UTC)"
      timespan: "'minute' for micro-batch streaming; 'day' for historical backfill"
      vwap: "Volume-weighted average price within the bar; null if unavailable"
      raw_payload: "Full JSON from Massive API for audit/replay; nullable"
      ingest_ts: "When Databricks received the row; always UTC; used for freshness checks"

  bronze_options_quotes:
    grain: "One row per (option_symbol, participant_ts) — one minute quote snapshot"
    partitioned_by: underlying
    volume_note: "This is the primary Big Data Volume source (>= 5M rows for capstone acceptance)"
    columns:
      option_symbol: "OCC format e.g. O:SPY251219C00600000 — encodes underlying, expiry, strike, right"
      underlying: "Parsed from option_symbol; e.g. SPY"
      expiry: "Option expiration date (parsed from OCC symbol)"
      strike: "Strike price in dollars (parsed from OCC symbol, divided by 1000)"
      right: "'C' = call, 'P' = put"
      midpoint: "(bid + ask) / 2; computed on ingestion"

  bronze_options_trades:
    grain: "One row per (option_symbol, participant_ts) — one minute trade bar"
    partitioned_by: underlying
    columns:
      open: "First trade price in the minute"
      high: "Highest trade price in the minute"
      low: "Lowest trade price in the minute"
      close: "Last trade price in the minute"
      volume: "Number of contracts traded in the minute"
      vwap: "Volume-weighted average price for the minute"

  bronze_sec_filings:
    grain: "One row per (accession_number, chunk_id) — one text chunk from a filing"
    partitioned_by: form_type
    variety_note: "SEC is the Big Data Variety source (unstructured HTML/XML/XBRL/TXT)"
    columns:
      accepted_ts: "EDGAR acceptance timestamp — CRITICAL for PIT joins (not filing_date)"
      filing_section: "Mapped section: item1, item1a, item7, item7a, item8, etc."
      chunk_text: "Cleaned text after HTML/XML stripping; 1000-2000 chars per chunk"
      raw_payload_ref: "S3/volume path to original filing document"

  bronze_cot:
    grain: "One row per (report_date, market_code) — one weekly COT report line"
    partitioned_by: none
    columns:
      release_ts: "CFTC publication timestamp — CRITICAL for PIT joins (not report_date)"
      report_date: "COT report week ending date (typically Tuesday)"
      lev_money_long: "Leveraged Money (hedge funds) long positions"
      lev_money_short: "Leveraged Money short positions"
      asset_mgr_long: "Asset Manager/Institutional long positions"

  gold_trading_signals:
    grain: "One row per (signal_id) = one ML prediction"
    partitioned_by: symbol
    columns:
      signal_id: "UUID; unique prediction identifier"
      direction: "'UP' or 'DOWN' — predicted 30-minute forward return direction"
      probability: "Model confidence [0, 1]; >0.5 = UP, <0.5 = DOWN"
      horizon: "Prediction horizon string, e.g. '30m'"
      feature_snapshot_id: "FK to gold_model_features — full lineage to source features"
      status: "ACTIVE (current), EXPIRED (past horizon), CONSUMED (used for order)"

  gold_model_features:
    grain: "One row per (symbol, prediction_ts) — PIT-joined feature vector"
    partitioned_by: symbol
    critical_rule: "Every feature column was available at or before prediction_ts"
"""

filters_yaml = """
# ============================================================
# FILTERS — Session rules, stale thresholds, exclusion patterns
# ============================================================

filters:
  regular_session_only:
    description: "Filter to US regular trading hours only"
    sql: "is_regular_session = true"
    applies_to: [silver_ohlcv]
    note: "Use for model training; pre/post-market has different liquidity dynamics"

  stale_signal_threshold:
    description: "Signals older than 5 minutes are stale for intraday trading"
    sql: "prediction_ts >= current_timestamp() - INTERVAL 5 MINUTES"
    applies_to: [gold_trading_signals]
    note: "Risk service blocks order intents based on stale signals"

  stale_market_data_threshold:
    description: "Bronze market data must be fresh within 2 minutes during session"
    sql: "ingest_ts >= current_timestamp() - INTERVAL 2 MINUTES"
    applies_to: [bronze_ohlcv, bronze_options_quotes]
    note: "Triggers freshness alert on dashboard if violated"

  exclude_stale_quotes:
    description: "Exclude stale, locked, or crossed quotes from options features"
    sql: "is_stale = false AND is_locked = false AND is_crossed = false"
    applies_to: [silver_options_quotes]

  pit_no_lookahead:
    description: "Point-in-time constraint: feature must be available before prediction"
    sql: "information_available_ts <= prediction_ts"
    applies_to: [gold_ohlcv_features, gold_options_features, gold_sec_features, gold_cot_features]
    critical: true
    test: "Automated assertion in CI: any violation fails the feature build"

  cot_forward_fill_rule:
    description: "COT data is weekly; forward-fill only until next official release"
    sql: "release_ts = (SELECT MAX(release_ts) FROM silver_cot_positions WHERE release_ts <= prediction_ts)"
    applies_to: [gold_cot_features]
    note: "Never backward-fill. COT is a slow regime feature, not an intraday trigger."

  minimum_volume_filter:
    description: "Exclude illiquid bars from feature computation"
    sql: "volume > 0"
    applies_to: [silver_ohlcv, silver_options_trades]

  sec_fair_access:
    description: "SEC EDGAR rate limit: <=10 requests/second total"
    applies_to: [etl/extract_edgar.py]
    enforcement: "Client-side throttle with 0.12s delay between requests"

  order_risk_checks:
    description: "Deterministic pre-trade checks before IBKR submission"
    checks:
      - "Symbol in allow-list (config/tickers.yaml universe)"
      - "Paper-account mode only"
      - "Quantity > 0 and notional <= MAX_ORDER_NOTIONAL ($25,000 default)"
      - "Position notional after fill <= MAX_POSITION_NOTIONAL ($50,000 default)"
      - "Buying power sufficient"
      - "No duplicate open order for same symbol+side"
      - "Signal not stale (< 5 min)"
      - "Market session is open or order type is limit"
    applies_to: [agent/guardrails.py]
"""

print("Ontology: table_semantics (", table_semantics_yaml.count("grain:"), "tables ) + filters (", filters_yaml.count("description:"), "rules )")

# COMMAND ----------

# DBTITLE 1,Write ontology YAML files to workspace
import os

base_dir = "/Workspace/Users/evangohsg@gmail.com/Capstone/quant_platform/ontology"
os.makedirs(base_dir, exist_ok=True)

# Write each ontology YAML
for name, content in [
    ("business_terms.yaml", business_terms_yaml),
    ("metric_definitions.yaml", metric_definitions_yaml),
    ("join_hints.yaml", join_hints_yaml),
    ("table_semantics.yaml", table_semantics_yaml),
    ("filters.yaml", filters_yaml),
]:
    path = os.path.join(base_dir, name)
    with open(path, "w") as f:
        f.write(content.strip())
    print(f"  ✓ {path}")

print(f"\nAll 5 ontology files written to {base_dir}/")

# COMMAND ----------

# DBTITLE 1,Scaffold Databricks App: app.yaml + app.py
import os

app_dir = "/Workspace/Users/evangohsg@gmail.com/Capstone/quant_platform"

# ---- app.yaml ----
app_yaml = """
command:
  - uvicorn
  - app:app
  - --host
  - 0.0.0.0
  - --port
  - "8000"

env:
  - name: CATALOG
    value: bootcamp_students
  - name: SCHEMA
    value: evangoh_capstone
""".strip()

with open(os.path.join(app_dir, "app.yaml"), "w") as f:
    f.write(app_yaml)
print("✓ app.yaml")

# ---- app.py (FastAPI backend) ----
app_py = '''
"""
quant_platform/app.py
FastAPI backend for the Mid-Frequency Quant Trading Databricks App.

Serves:
  - /api/signals         GET  - Latest ML trading signals
  - /api/market/{symbol} GET  - OHLCV + options features for a symbol
  - /api/sec/{symbol}    GET  - SEC filing sections/events
  - /api/cot/{asset}     GET  - COT positioning features
  - /api/portfolio       GET  - IBKR paper positions
  - /api/orders/intents  POST - Create order intent
  - /api/orders/{id}/approve  POST - Approve and route to IBKR
  - /api/orders/{id}/cancel   POST - Cancel order
  - /api/watchlists      GET/POST - Watchlist CRUD
  - /api/agent/chat      POST - AI agent conversation
  - /api/analytics/health GET - System health metrics
  - /api/slippage        POST - Transaction cost calculation
  - /*                   GET  - React SPA (static files)
"""
import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

app = FastAPI(title="Quant Trading Platform", version="1.0.0")

CATALOG = os.getenv("CATALOG", "bootcamp_students")
SCHEMA  = os.getenv("SCHEMA", "evangoh_capstone")


# ---- Signal Endpoints ----
@app.get("/api/signals")
async def get_signals(symbol: Optional[str] = None, limit: int = 20):
    """Latest ML trading signals from gold_trading_signals."""
    # TODO: Wire to delta_adapter.latest_signals()
    return {"signals": [], "count": 0}


@app.get("/api/market/{symbol}")
async def get_market(symbol: str, start: Optional[str] = None, end: Optional[str] = None):
    """OHLCV + options features for a symbol."""
    # TODO: Wire to delta_adapter.market_features()
    return {"symbol": symbol, "ohlcv": [], "options": []}


@app.get("/api/sec/{symbol}")
async def get_sec_filings(symbol: str, form_type: Optional[str] = None, query: Optional[str] = None):
    """SEC filing sections and extracted events."""
    # TODO: Wire to services/sec_analyzer.py + delta read
    return {"symbol": symbol, "filings": []}


@app.get("/api/cot/{asset}")
async def get_cot(asset: str):
    """COT positioning features."""
    # TODO: Wire to delta_adapter.read_table("gold_cot_features")
    return {"asset": asset, "positioning": {}}


# ---- Portfolio & Orders ----
@app.get("/api/portfolio")
async def get_portfolio():
    """IBKR paper positions, buying power, open orders."""
    # TODO: Wire to db/lakebase_client.py
    return {"positions": [], "buying_power": 0}


class OrderIntent(BaseModel):
    symbol: str
    side: str  # BUY or SELL
    quantity: float
    order_type: str = "MARKET"  # MARKET or LIMIT
    limit_price: Optional[float] = None
    signal_id: Optional[str] = None


@app.post("/api/orders/intents")
async def create_order_intent(intent: OrderIntent):
    """Create PENDING_APPROVAL order intent in Lakebase."""
    # TODO: Wire to agent/guardrails.py + db/lakebase_client.py
    return {"order_id": "placeholder", "status": "PENDING_APPROVAL"}


@app.post("/api/orders/{order_id}/approve")
async def approve_order(order_id: str):
    """Approve order and route to IBKR execution bridge."""
    # TODO: Wire to execution/bridge.py
    return {"order_id": order_id, "status": "SUBMITTED"}


@app.post("/api/orders/{order_id}/cancel")
async def cancel_order(order_id: str):
    """Cancel order."""
    # TODO: Wire to execution/bridge.py
    return {"order_id": order_id, "status": "CANCELLED"}


# ---- Watchlists ----
@app.get("/api/watchlists")
async def get_watchlists():
    # TODO: Wire to db/lakebase_client.py
    return {"watchlists": []}


class WatchlistItem(BaseModel):
    symbol: str


@app.post("/api/watchlists")
async def add_to_watchlist(item: WatchlistItem):
    # TODO: Wire to db/lakebase_client.py
    return {"symbol": item.symbol, "added": True}


# ---- AI Agent ----
class AgentMessage(BaseModel):
    message: str
    conversation_id: Optional[str] = None


@app.post("/api/agent/chat")
async def agent_chat(msg: AgentMessage):
    """AI agent conversation with tool traces."""
    # TODO: Wire to agent/orchestrator.py (LangGraph)
    return {"response": "", "tool_calls": [], "conversation_id": msg.conversation_id}


# ---- Slippage Calculator ----
class SlippageRequest(BaseModel):
    ticker: str
    asset_type: str = "stock"  # stock or option
    quantity: float
    price: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    adv: Optional[float] = None


@app.post("/api/slippage")
async def calculate_slippage(req: SlippageRequest):
    """Transaction cost calculation using Almgren-Chriss model."""
    # TODO: Wire to etl/slippage.py :: calculate_costs()
    return {"total_cost": 0, "breakdown": {}}


# ---- Analytics / Health ----
@app.get("/api/analytics/health")
async def health():
    """System health: freshness, latency, pipeline status."""
    # TODO: Wire to analytics tables
    return {"status": "ok", "freshness": {}, "latency": {}}


# ---- Static React SPA ----
frontend_dir = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.isdir(frontend_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dir, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        return FileResponse(os.path.join(frontend_dir, "index.html"))
'''.strip()

with open(os.path.join(app_dir, "app.py"), "w") as f:
    f.write(app_py)
print("✓ app.py")

# ---- requirements.txt ----
requirements = """
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
pydantic>=2.0
databricks-sdk>=0.20.0
databricks-sql-connector>=3.0.0
langchain>=0.1.0
langchain-community>=0.1.0
langgraph>=0.0.20
mlflow>=2.10.0
polygon-api-client>=1.12.0
ibapi>=10.19.0
requests>=2.31.0
loguru>=0.7.0
yfinance>=0.2.30
sentence-transformers>=2.2.0
beautifulsoup4>=4.12.0
lxml>=4.9.0
""".strip()

with open(os.path.join(app_dir, "requirements.txt"), "w") as f:
    f.write(requirements)
print("✓ requirements.txt")

print(f"\nDatabricks App scaffold written to {app_dir}/")

# COMMAND ----------

# DBTITLE 1,Create directory structure + copy KEEP components
import os
import shutil

BASE     = "/Workspace/Users/evangohsg@gmail.com/Capstone/quant_platform"
IBKR_SRC = "/Workspace/Users/evangohsg@gmail.com/Capstone/IBKR_workbench"
RAG_SRC  = "/Workspace/Users/evangohsg@gmail.com/Rag_workbench"

# Create all subdirectories
for d in [
    "etl", "services", "services/models", "db", "agent", "execution",
    "config", "ontology", "pipelines", "ml", "tests/bronze", "tests/silver",
    "tests/gold", "docs", "frontend",
]:
    os.makedirs(os.path.join(BASE, d), exist_ok=True)

# ---- Copy IBKR Workbench KEEP components -> etl/ + config/ ----
ibkr_etl_keep = [
    "polygon_client.py", "extract_polygon.py", "extract_options.py",
    "extract_edgar.py", "extract_cot.py", "extract_stocks.py",
    "extract_yfinance.py", "ibkr_client.py", "slippage.py", "utils.py",
    "__init__.py",
]
for f in ibkr_etl_keep:
    src = os.path.join(IBKR_SRC, "etl", f)
    dst = os.path.join(BASE, "etl", f)
    if os.path.exists(src):
        shutil.copy2(src, dst)
        print(f"  etl/{f} ← IBKR")
    else:
        print(f"  etl/{f} (not found in IBKR, will create stub)")

ibkr_config_keep = ["tickers.py", "tickers.yaml", "update_tickers.py", "__init__.py"]
for f in ibkr_config_keep:
    src = os.path.join(IBKR_SRC, "config", f)
    dst = os.path.join(BASE, "config", f)
    if os.path.exists(src):
        shutil.copy2(src, dst)
        print(f"  config/{f} ← IBKR")

# ---- Copy RAG Workbench KEEP components -> services/ ----
# Note: RAG workbench is a git folder; files may be virtual.
# We check and copy what's available, stub the rest.
rag_services_map = {
    # source filename in api/services/ -> target filename in services/
    "xbrl_parser.py": "xbrl_parser.py",
    "xbrl_validator.py": "xbrl_validator.py", 
    "xbrl_mapper.py": "xbrl_mapper.py",
    "financial_calc.py": "financial_calc.py",
    "sec_client.py": "sec_client.py",
    "sec_analyzer.py": "sec_analyzer.py",
    "edgar_adapter.py": "edgar_adapter.py",
    "_edgar_identity.py": "_edgar_identity.py",
    "graph_rag_engine.py": "graph_rag_engine.py",
    "sentiment.py": "sentiment.py",
    "schema_validator.py": "schema_validator.py",
    "semantic_validator.py": "semantic_validator.py",
    "verifier.py": "verifier.py",
    "verification.py": "verification.py",
    "confidence_scorer.py": "confidence_scorer.py",
    "calibration.py": "calibration.py",
    "peer_comparison.py": "peer_comparison.py",
    "langgraph_engine.py": "langgraph_engine.py",
    "chat_engine.py": "chat_engine.py",
    "structure_chunker.py": "structure_chunker.py",
}

rag_api_dir = os.path.join(RAG_SRC, "api", "services")
for src_name, dst_name in rag_services_map.items():
    src = os.path.join(rag_api_dir, src_name)
    dst = os.path.join(BASE, "services", dst_name)
    if os.path.exists(src):
        shutil.copy2(src, dst)
        print(f"  services/{dst_name} ← RAG")
    else:
        # Create stub for git-managed files
        with open(dst, "w") as f:
            f.write(f'"""\n{dst_name}\nStub — copy from Rag_workbench/api/services/{src_name} after git clone.\n"""\n')
        print(f"  services/{dst_name} (stub — clone RAG repo to populate)")

# Create __init__.py files
for d in ["etl", "services", "services/models", "db", "agent", "execution", "config", "pipelines", "ml"]:
    init_path = os.path.join(BASE, d, "__init__.py")
    if not os.path.exists(init_path):
        with open(init_path, "w") as f:
            f.write("")

print("\n\u2713 Directory structure created and KEEP components copied")

# COMMAND ----------

# DBTITLE 1,Write db/ adapter modules + agent/ stubs + config/settings.py
import os

BASE = "/Workspace/Users/evangohsg@gmail.com/Capstone/quant_platform"

# ---- db/delta_adapter.py (the key rewiring layer) ----
# Already defined above in the notebook cell; write the module file.
delta_adapter_path = os.path.join(BASE, "db", "delta_adapter.py")
with open(delta_adapter_path, "w") as f:
    f.write('''"""\ndb/delta_adapter.py\nDrop-in replacement for IBKR_workbench/db/database.py.\nAll ETL extraction clients call this instead of DuckDB get_connection().\n"""\nfrom pyspark.sql import SparkSession, DataFrame\nfrom pyspark.sql import functions as F\nfrom datetime import datetime, timezone\nfrom typing import List, Dict, Optional\n\nCATALOG = "bootcamp_students"\nSCHEMA  = "evangoh_capstone"\n\ndef _fqn(table: str) -> str:\n    return f"{CATALOG}.{SCHEMA}.{table}"\n\ndef _spark() -> SparkSession:\n    return SparkSession.builder.getOrCreate()\n\ndef _now() -> datetime:\n    return datetime.now(timezone.utc)\n\n# -- Compatibility shim: replaces get_connection() for ETL clients --\ndef get_connection():\n    """Returns a DeltaConnectionShim that mimics DuckDB connection.execute().\n    ETL clients call conn.execute("INSERT ...", params) which this translates to Delta appends.\n    """\n    return DeltaConnectionShim()\n\nclass DeltaConnectionShim:\n    """Shim that captures DuckDB-style INSERT calls and routes to Delta writes."""\n    def __init__(self):\n        self._buffer = {}  # table_name -> list of row dicts\n    \n    def execute(self, sql: str, params=None):\n        """Intercept INSERT OR IGNORE INTO <table> (...) VALUES (?, ...)"""\n        import re\n        m = re.match(r"INSERT\\s+OR\\s+IGNORE\\s+INTO\\s+(\\w+)", sql, re.IGNORECASE)\n        if not m:\n            m = re.match(r"INSERT\\s+INTO\\s+(\\w+)", sql, re.IGNORECASE)\n        if m:\n            table = m.group(1)\n            # Map old DuckDB table names to new bronze names\n            table_map = {\n                "polygon_bars": "bronze_ohlcv",\n                "polygon_snapshots": "bronze_ohlcv",\n                "polygon_option_snapshots": "bronze_options_quotes",\n                "polygon_option_bars": "bronze_options_trades",\n                "edgar_filings": "bronze_sec_filings",\n                "edgar_facts": "bronze_sec_filings",\n                "cot_reports": "bronze_cot",\n                "stock_quotes": "bronze_ohlcv",\n                "option_quotes": "bronze_options_quotes",\n            }\n            target = table_map.get(table, table)\n            if target not in self._buffer:\n                self._buffer[target] = []\n            if params:\n                self._buffer[target].append(params)\n    \n    def __enter__(self):\n        return self\n    \n    def __exit__(self, *args):\n        self.flush()\n    \n    def flush(self):\n        """Write all buffered rows to Delta tables."""\n        spark = _spark()\n        for table, rows in self._buffer.items():\n            if rows:\n                df = spark.createDataFrame(rows)\n                df.write.format("delta").mode("append").saveAsTable(_fqn(table))\n        self._buffer.clear()\n\n# -- Direct writers for new code --\ndef write_bronze(table: str, rows: List[Dict]) -> int:\n    if not rows:\n        return 0\n    spark = _spark()\n    ts = _now()\n    for r in rows:\n        r["ingest_ts"] = ts\n    df = spark.createDataFrame(rows)\n    df.write.format("delta").mode("append").saveAsTable(_fqn(table))\n    return len(rows)\n\ndef read_table(table: str, filters: Optional[str] = None, limit: int = 1000) -> DataFrame:\n    spark = _spark()\n    df = spark.table(_fqn(table))\n    if filters:\n        df = df.where(filters)\n    return df.limit(limit)\n\ndef read_sql(query: str) -> DataFrame:\n    return _spark().sql(query)\n\ndef latest_signals(symbol: Optional[str] = None, limit: int = 20) -> DataFrame:\n    spark = _spark()\n    df = spark.table(_fqn("gold_trading_signals"))\n    if symbol:\n        df = df.where(F.col("symbol") == symbol)\n    return df.orderBy(F.col("prediction_ts").desc()).limit(limit)\n\ndef market_features(symbol: str, start_ts: str, end_ts: str) -> DataFrame:\n    spark = _spark()\n    ohlcv = spark.table(_fqn("gold_ohlcv_features")).where(\n        (F.col("symbol") == symbol) & (F.col("feature_ts").between(start_ts, end_ts))\n    )\n    opts = spark.table(_fqn("gold_options_features")).where(\n        (F.col("symbol") == symbol) & (F.col("feature_ts").between(start_ts, end_ts))\n    )\n    return ohlcv.join(opts, ["symbol", "feature_ts"], "left")\n''')
print("✓ db/delta_adapter.py")

# ---- config/settings.py ----
with open(os.path.join(BASE, "config", "settings.py"), "w") as f:
    f.write('''"""\nconfig/settings.py\nUnified configuration for the quant platform.\n"""\nimport os\n\n# Unity Catalog\nCATALOG = os.getenv("CATALOG", "bootcamp_students")\nSCHEMA  = os.getenv("SCHEMA", "evangoh_capstone")\n\n# API Keys (from Databricks Secrets)\nPOLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")\nEDGAR_EMAIL     = os.getenv("EDGAR_EMAIL", "research@example.com")\n\n# IBKR Paper Trading\nTWS_HOST      = os.getenv("TWS_HOST", "127.0.0.1")\nTWS_PORT      = int(os.getenv("TWS_PORT", "7497"))  # 7497=paper, 7496=live\nTWS_CLIENT_ID = int(os.getenv("TWS_CLIENT_ID", "1"))\n\n# Risk Limits\nMAX_ORDER_NOTIONAL    = float(os.getenv("MAX_ORDER_NOTIONAL", "25000"))\nMAX_POSITION_NOTIONAL = float(os.getenv("MAX_POSITION_NOTIONAL", "50000"))\nSTALE_SIGNAL_MINUTES  = int(os.getenv("STALE_SIGNAL_MINUTES", "5"))\n\n# Model\nMODEL_ENDPOINT = os.getenv("MODEL_ENDPOINT", "")\nPREDICTION_HORIZON = os.getenv("PREDICTION_HORIZON", "30m")\n\n# Chat Provider\nCHAT_PROVIDER = os.getenv("CHAT_PROVIDER", "databricks")  # databricks, openai, anthropic\n\n# Universe\nTICKER_YAML = os.getenv("TICKER_YAML", "config/tickers.yaml")\n''')
print("✓ config/settings.py")

# ---- agent/tools_retrieval.py (stub with all 8 tools) ----
with open(os.path.join(BASE, "agent", "tools_retrieval.py"), "w") as f:
    f.write('''"""\nagent/tools_retrieval.py\nRead-only retrieval tools for the AI agent.\nEach tool reads from Delta tables or Lakebase and enforces PIT constraints.\n"""\nfrom db.delta_adapter import read_table, latest_signals, market_features, read_sql\nfrom typing import Optional\n\ndef get_latest_signal(symbol: str) -> dict:\n    """Retrieve the latest ML trading signal and confidence score."""\n    df = latest_signals(symbol, limit=1)\n    rows = df.collect()\n    return rows[0].asDict() if rows else {}\n\ndef get_market_features(symbol: str, start_time: str, end_time: str) -> list:\n    """Retrieve OHLCV + options features for a symbol in a time range."""\n    df = market_features(symbol, start_time, end_time)\n    return [r.asDict() for r in df.collect()]\n\ndef get_options_features(symbol: str, expiry: Optional[str] = None) -> list:\n    """Retrieve IV, skew, Greeks, put/call ratio, volume anomaly."""\n    filters = f"symbol = \'{symbol}\'"\n    if expiry:\n        filters += f" AND expiry = \'{expiry}\'"\n    df = read_table("gold_options_features", filters=filters)\n    return [r.asDict() for r in df.collect()]\n\ndef search_sec_filings(symbol: str, query: Optional[str] = None, form_type: Optional[str] = None) -> list:\n    """Search recent SEC filing sections and extracted events."""\n    filters = f"ticker = \'{symbol}\'"\n    if form_type:\n        filters += f" AND form_type = \'{form_type}\'"\n    df = read_table("silver_sec_sections", filters=filters, limit=50)\n    results = [r.asDict() for r in df.collect()]\n    if query:\n        results = [r for r in results if query.lower() in (r.get("chunk_text", "") or "").lower()]\n    return results\n\ndef get_cot_positioning(mapped_asset: str) -> dict:\n    """Retrieve CFTC COT positioning and regime features."""\n    df = read_table("gold_cot_features", filters=f"mapped_asset = \'{mapped_asset}\'", limit=1)\n    rows = df.orderBy("report_date", ascending=False).collect()\n    return rows[0].asDict() if rows else {}\n\ndef get_portfolio_positions() -> list:\n    """Retrieve current paper-trading positions from Lakebase."""\n    # TODO: Wire to db/lakebase_client.py\n    return []\n\ndef get_open_orders() -> list:\n    """Retrieve active paper orders from Lakebase."""\n    # TODO: Wire to db/lakebase_client.py\n    return []\n\ndef get_watchlist() -> list:\n    """Retrieve securities currently being monitored from Lakebase."""\n    # TODO: Wire to db/lakebase_client.py\n    return []\n\ndef get_model_metrics(model_version: Optional[str] = None) -> dict:\n    """Retrieve validation and live monitoring metrics from MLflow/analytics."""\n    # TODO: Wire to MLflow\n    return {}\n''')
print("✓ agent/tools_retrieval.py")

# ---- agent/tools_write.py ----
with open(os.path.join(BASE, "agent", "tools_write.py"), "w") as f:
    f.write('''"""\nagent/tools_write.py\nWrite tools for the AI agent. Each writes to Lakebase operational tables.\n"""\nfrom typing import Optional\nimport uuid\nfrom datetime import datetime, timezone\n\ndef add_to_watchlist(symbol: str, user_id: str = "default") -> dict:\n    """Insert/update Lakebase watchlist. Autonomous after user instruction."""\n    # TODO: Wire to db/lakebase_client.py\n    return {"watchlist_id": str(uuid.uuid4()), "symbol": symbol, "status": "added"}\n\ndef save_research_note(symbol: str, note_text: str, signal_id: Optional[str] = None, user_id: str = "default") -> dict:\n    """Insert Lakebase research_notes. Autonomous after user instruction."""\n    return {"note_id": str(uuid.uuid4()), "symbol": symbol, "status": "saved"}\n\ndef create_order_intent(symbol: str, side: str, quantity: float, order_type: str = "MARKET",\n                        limit_price: Optional[float] = None, signal_id: Optional[str] = None,\n                        user_id: str = "default") -> dict:\n    """Create PENDING_APPROVAL Lakebase order intent. No broker action yet."""\n    # TODO: Run agent/guardrails.py checks first\n    return {"order_id": str(uuid.uuid4()), "status": "PENDING_APPROVAL"}\n\ndef approve_and_place_paper_order(order_id: str, user_id: str = "default") -> dict:\n    """Risk re-check then submit to IBKR bridge. Requires explicit human approval."""\n    # TODO: Wire to execution/bridge.py\n    return {"order_id": order_id, "status": "SUBMITTED"}\n\ndef cancel_paper_order(order_id: str) -> dict:\n    """Request cancellation through IBKR and update state."""\n    return {"order_id": order_id, "status": "CANCEL_REQUESTED"}\n\ndef record_agent_action(user_id: str, tool_name: str, action_type: str,\n                        input_summary: str, output_summary: str, status: str = "success") -> dict:\n    """Audit every tool call/result. Automatic system action."""\n    return {"action_id": str(uuid.uuid4()), "tool_name": tool_name, "status": status}\n''')
print("✓ agent/tools_write.py")

# ---- agent/guardrails.py ----
with open(os.path.join(BASE, "agent", "guardrails.py"), "w") as f:
    f.write('''"""\nagent/guardrails.py\nDeterministic risk checks for order intents.\nFailed checks return structured reasons; no broker call occurs.\n"""\nfrom config.settings import MAX_ORDER_NOTIONAL, MAX_POSITION_NOTIONAL, STALE_SIGNAL_MINUTES\nfrom typing import Optional, List, Tuple\nfrom datetime import datetime, timezone, timedelta\n\ndef validate_order(\n    symbol: str,\n    side: str,\n    quantity: float,\n    price: float,\n    order_type: str,\n    signal_prediction_ts: Optional[datetime] = None,\n    current_position_notional: float = 0.0,\n    buying_power: float = 100000.0,\n    open_orders_same_symbol_side: int = 0,\n    allowed_symbols: Optional[set] = None,\n    is_paper: bool = True,\n) -> Tuple[bool, List[str]]:\n    """Run all pre-trade checks. Returns (passed, list_of_failure_reasons)."""\n    failures = []\n    notional = price * quantity\n    \n    # 1. Allow-listed symbols\n    if allowed_symbols and symbol not in allowed_symbols:\n        failures.append(f"Symbol {symbol} not in allow-list")\n    \n    # 2. Paper-account only\n    if not is_paper:\n        failures.append("Only paper-account trading is allowed")\n    \n    # 3. Positive quantity\n    if quantity <= 0:\n        failures.append(f"Quantity must be positive, got {quantity}")\n    \n    # 4. Max order notional\n    if notional > MAX_ORDER_NOTIONAL:\n        failures.append(f"Order notional ${notional:,.0f} exceeds max ${MAX_ORDER_NOTIONAL:,.0f}")\n    \n    # 5. Max position notional\n    if current_position_notional + notional > MAX_POSITION_NOTIONAL:\n        failures.append(f"Position would exceed max ${MAX_POSITION_NOTIONAL:,.0f}")\n    \n    # 6. Buying power\n    if notional > buying_power:\n        failures.append(f"Insufficient buying power (${buying_power:,.0f} < ${notional:,.0f})")\n    \n    # 7. Duplicate order\n    if open_orders_same_symbol_side > 0:\n        failures.append(f"Duplicate: {open_orders_same_symbol_side} open {side} order(s) for {symbol}")\n    \n    # 8. Stale signal\n    if signal_prediction_ts:\n        age = datetime.now(timezone.utc) - signal_prediction_ts\n        if age > timedelta(minutes=STALE_SIGNAL_MINUTES):\n            failures.append(f"Signal is stale ({age.total_seconds()/60:.1f}min > {STALE_SIGNAL_MINUTES}min)")\n    \n    # 9. Valid order type\n    if order_type not in ("MARKET", "LIMIT"):\n        failures.append(f"Unsupported order type: {order_type}")\n    \n    return (len(failures) == 0, failures)\n''')
print("✓ agent/guardrails.py")

print("\n\u2713 All module files written")

# COMMAND ----------

# DBTITLE 1,Verify: List created project structure
import os

BASE = "/Workspace/Users/evangohsg@gmail.com/Capstone/quant_platform"

def tree(path, prefix="", max_depth=3, depth=0):
    if depth >= max_depth:
        return
    entries = sorted(os.listdir(path))
    dirs = [e for e in entries if os.path.isdir(os.path.join(path, e)) and not e.startswith(".")]
    files = [e for e in entries if os.path.isfile(os.path.join(path, e))]
    
    for f in files:
        size = os.path.getsize(os.path.join(path, f))
        label = f"{f} ({size:,} bytes)" if size > 0 else f"{f} (empty)"
        print(f"{prefix}├── {label}")
    for i, d in enumerate(dirs):
        connector = "└──" if i == len(dirs) - 1 and not files else "├──"
        print(f"{prefix}{connector} {d}/")
        extension = "    " if i == len(dirs) - 1 else "│   "
        tree(os.path.join(path, d), prefix + extension, max_depth, depth + 1)

print("quant_platform/")
tree(BASE)

# Count files
total_files = sum(len(f) for _, _, f in os.walk(BASE))
total_dirs = sum(len(d) for _, d, _ in os.walk(BASE))
print(f"\n\u2500\u2500 Total: {total_files} files in {total_dirs} directories")

# COMMAND ----------

# DBTITLE 1,Install dependencies
# %pip install polygon-api-client -q

# COMMAND ----------

# DBTITLE 1,OPTION A: REST API — Stock Minute + Day + Options + Economic (works NOW)
# ══════════════════════════════════════════════════════════════════════════════
# OPTION A: Polygon REST API
# ─ Uses your existing polygon_api_key (already verified working)
# ─ No S3 credentials needed
# ─ Covers: stock minute+day bars, options snapshots, economic metrics
# ─ Tradeoff: rate-limited, ~12s per ticker for minute bars
# ══════════════════════════════════════════════════════════════════════════════
from polygon import RESTClient
from pyspark.sql import SparkSession
from pyspark.sql.types import *
from datetime import datetime, timezone, date as dt_date, timedelta
import time

api_key = dbutils.secrets.get(scope="evangoh_capstone", key="polygon_api_key")
client = RESTClient(api_key=api_key)
spark = SparkSession.builder.getOrCreate()

CATALOG_SCHEMA = "bootcamp_students.evangoh_capstone"
ingest_ts = datetime.now(timezone.utc)

TICKERS = [
    # Mag 7
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
    # Semiconductors
    "AMD", "INTC", "QCOM", "AVGO", "MU", "MRVL", "AMAT", "LRCX",
    # ETFs
    "SPY", "QQQ", "IWM", "DIA", "XLF", "XLK", "XLE",
    # Financials
    "JPM", "GS", "BAC", "MS",
    # Other
    "NFLX", "CRM", "UBER", "COIN", "XOM", "JNJ", "V", "WMT",
]

ohlcv_schema = StructType([
    StructField("symbol", StringType()),
    StructField("event_ts", TimestampType()),
    StructField("open", DoubleType()),
    StructField("high", DoubleType()),
    StructField("low", DoubleType()),
    StructField("close", DoubleType()),
    StructField("volume", LongType()),
    StructField("vwap", DoubleType()),
    StructField("trade_count", IntegerType()),
    StructField("timespan", StringType()),
    StructField("source", StringType()),
    StructField("raw_payload", StringType()),
    StructField("ingest_ts", TimestampType()),
])

# ──────────────────────────────────────────────────────────────────────
# A1: Stock Minute Bars (REST API) → bronze_ohlcv
#     ~50K limit per call; fetches 12 months of minute bars per ticker
# ──────────────────────────────────────────────────────────────────────
print("="*70)
print("  A1: Stock MINUTE Bars (REST API) → bronze_ohlcv")
print("="*70)

from_date = (dt_date.today() - timedelta(days=365)).isoformat()
to_date = dt_date.today().isoformat()
grand_total = 0

for i, ticker in enumerate(TICKERS, 1):
    try:
        aggs = list(client.get_aggs(ticker, 1, "minute", from_date, to_date, adjusted=True, limit=50000))
        if aggs:
            rows = []
            for a in aggs:
                ts = datetime.fromtimestamp(a.timestamp / 1000, tz=timezone.utc) if a.timestamp else None
                rows.append((
                    ticker, ts,
                    float(a.open) if a.open else None,
                    float(a.high) if a.high else None,
                    float(a.low) if a.low else None,
                    float(a.close) if a.close else None,
                    int(a.volume) if a.volume else None,
                    float(a.vwap) if a.vwap else None,
                    int(a.transactions) if a.transactions else None,
                    "minute", "polygon_rest", None, ingest_ts,
                ))
            df = spark.createDataFrame(rows, schema=ohlcv_schema)
            df.write.format("delta").mode("append").option("mergeSchema", "true") \
                .saveAsTable(f"{CATALOG_SCHEMA}.bronze_ohlcv")
            grand_total += len(rows)
        print(f"  [{i:2d}/{len(TICKERS)}] {ticker:<6} {len(aggs):>7,} minute bars  (cum: {grand_total:>10,})")
    except Exception as e:
        print(f"  [{i:2d}/{len(TICKERS)}] {ticker:<6} ERROR: {str(e)[:120]}")
    time.sleep(12)  # Polygon free-tier: 5 calls/min

print(f"\n  ✓ Stock minute bars: {grand_total:,} rows")

# ──────────────────────────────────────────────────────────────────────
# A2: Stock Day Bars (REST API) → bronze_ohlcv
# ──────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("  A2: Stock DAY Bars (REST API) → bronze_ohlcv")
print("="*70)

day_from = (dt_date.today() - timedelta(days=5*365)).isoformat()
grand_total_day = 0

for i, ticker in enumerate(TICKERS, 1):
    try:
        aggs = list(client.get_aggs(ticker, 1, "day", day_from, to_date, adjusted=True, limit=50000))
        if aggs:
            rows = []
            for a in aggs:
                ts = datetime.fromtimestamp(a.timestamp / 1000, tz=timezone.utc) if a.timestamp else None
                rows.append((
                    ticker, ts,
                    float(a.open) if a.open else None,
                    float(a.high) if a.high else None,
                    float(a.low) if a.low else None,
                    float(a.close) if a.close else None,
                    int(a.volume) if a.volume else None,
                    float(a.vwap) if a.vwap else None,
                    int(a.transactions) if a.transactions else None,
                    "day", "polygon_rest", None, ingest_ts,
                ))
            df = spark.createDataFrame(rows, schema=ohlcv_schema)
            df.write.format("delta").mode("append").option("mergeSchema", "true") \
                .saveAsTable(f"{CATALOG_SCHEMA}.bronze_ohlcv")
            grand_total_day += len(rows)
        print(f"  [{i:2d}/{len(TICKERS)}] {ticker:<6} {len(aggs):>6,} day bars  (cum: {grand_total_day:>8,})")
    except Exception as e:
        print(f"  [{i:2d}/{len(TICKERS)}] {ticker:<6} ERROR: {str(e)[:120]}")
    time.sleep(0.2)

print(f"\n  ✓ Stock day bars: {grand_total_day:,} rows")

# ──────────────────────────────────────────────────────────────────────
# A3: Options Chain Snapshots (REST API) → bronze_options_quotes
# ──────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("  A3: Options Chain Snapshots (REST API) → bronze_options_quotes")
print("="*70)

options_schema = StructType([
    StructField("option_symbol", StringType()),
    StructField("underlying", StringType()),
    StructField("expiry", DateType()),
    StructField("strike", DoubleType()),
    StructField("right", StringType()),
    StructField("bid", DoubleType()),
    StructField("ask", DoubleType()),
    StructField("bid_size", IntegerType()),
    StructField("ask_size", IntegerType()),
    StructField("midpoint", DoubleType()),
    StructField("participant_ts", TimestampType()),
    StructField("sequence_id", LongType()),
    StructField("source", StringType()),
    StructField("raw_payload", StringType()),
    StructField("ingest_ts", TimestampType()),
    StructField("last_price", DoubleType()),
    StructField("volume", LongType()),
    StructField("open_interest", LongType()),
    StructField("implied_volatility", DoubleType()),
    StructField("delta", DoubleType()),
    StructField("gamma", DoubleType()),
    StructField("theta", DoubleType()),
    StructField("vega", DoubleType()),
])

OPTION_UNDERLYINGS = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "TSLA",
                      "META", "AMD", "AMZN", "GOOGL", "JPM", "XOM"]
options_total = 0

for i, underlying in enumerate(OPTION_UNDERLYINGS, 1):
    try:
        chain = list(client.list_snapshot_options_chain(underlying))
        rows = []
        for snap in chain:
            det = snap.details if hasattr(snap, 'details') else None
            day = snap.day if hasattr(snap, 'day') else None
            grk = snap.greeks if hasattr(snap, 'greeks') else None
            lq = snap.last_quote if hasattr(snap, 'last_quote') else None

            bid = float(lq.bid) if lq and hasattr(lq, 'bid') and lq.bid else None
            ask = float(lq.ask) if lq and hasattr(lq, 'ask') and lq.ask else None
            mid = (bid + ask) / 2 if bid and ask else None
            bid_sz = int(lq.bidsize) if lq and hasattr(lq, 'bidsize') and lq.bidsize else None
            ask_sz = int(lq.asksize) if lq and hasattr(lq, 'asksize') and lq.asksize else None
            exp_str = str(det.expiration_date) if det and hasattr(det, 'expiration_date') else None
            exp_date = dt_date.fromisoformat(exp_str) if exp_str else None

            rows.append((
                det.ticker if det else None, underlying, exp_date,
                float(det.strike_price) if det and hasattr(det, 'strike_price') else None,
                det.contract_type if det and hasattr(det, 'contract_type') else None,
                bid, ask, bid_sz, ask_sz, mid,
                ingest_ts, None, "polygon_rest", None, ingest_ts,
                float(day.close) if day and hasattr(day, 'close') and day.close else None,
                int(day.volume) if day and hasattr(day, 'volume') and day.volume else None,
                int(snap.open_interest) if hasattr(snap, 'open_interest') and snap.open_interest else None,
                float(snap.implied_volatility) if hasattr(snap, 'implied_volatility') and snap.implied_volatility else None,
                float(grk.delta) if grk and hasattr(grk, 'delta') and grk.delta else None,
                float(grk.gamma) if grk and hasattr(grk, 'gamma') and grk.gamma else None,
                float(grk.theta) if grk and hasattr(grk, 'theta') and grk.theta else None,
                float(grk.vega) if grk and hasattr(grk, 'vega') and grk.vega else None,
            ))

        if rows:
            df = spark.createDataFrame(rows, schema=options_schema)
            df.write.format("delta").mode("append").option("mergeSchema", "true") \
                .saveAsTable(f"{CATALOG_SCHEMA}.bronze_options_quotes")
            options_total += len(rows)
        print(f"  [{i:2d}/{len(OPTION_UNDERLYINGS)}] {underlying:<6} {len(rows):>7,} contracts  (cum: {options_total:>9,})")
    except Exception as e:
        print(f"  [{i:2d}/{len(OPTION_UNDERLYINGS)}] {underlying:<6} ERROR: {str(e)[:120]}")
    time.sleep(0.3)

print(f"\n  ✓ Options snapshots: {options_total:,} rows")

# ──────────────────────────────────────────────────────────────────────
# A4: Stock Financials + Forex + Crypto + Indices → bronze_economic_metrics
# ──────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("  A4: Economic Metrics (REST API) → bronze_economic_metrics")
print("="*70)

econ_schema = StructType([
    StructField("metric_type", StringType()),
    StructField("symbol", StringType()),
    StructField("metric_name", StringType()),
    StructField("metric_value", DoubleType()),
    StructField("unit", StringType()),
    StructField("period", StringType()),
    StructField("fiscal_year", IntegerType()),
    StructField("event_ts", TimestampType()),
    StructField("source", StringType()),
    StructField("ingest_ts", TimestampType()),
])

# A4a: Stock financials
print("\n  ── Financials ──")
fin_total = 0
for i, ticker in enumerate(TICKERS, 1):
    try:
        fins = list(client.vx.list_stock_financials(ticker=ticker, limit=100))
        rows = []
        for f in fins:
            fy = f.fiscal_year if hasattr(f, 'fiscal_year') else None
            fp = f.fiscal_period if hasattr(f, 'fiscal_period') else None
            fd = f.filing_date if hasattr(f, 'filing_date') else None
            filing_ts = datetime.strptime(fd, "%Y-%m-%d").replace(tzinfo=timezone.utc) if fd else ingest_ts
            if hasattr(f, 'financials'):
                for stmt_name in ['income_statement', 'balance_sheet', 'cash_flow_statement', 'comprehensive_income']:
                    stmt = getattr(f.financials, stmt_name, None)
                    if stmt is None: continue
                    for metric_name, metric_obj in vars(stmt).items():
                        if metric_obj is None or not hasattr(metric_obj, 'value') or metric_obj.value is None: continue
                        unit_str = metric_obj.unit if hasattr(metric_obj, 'unit') else "USD"
                        rows.append(("financial_statement", ticker, f"{stmt_name}.{metric_name}",
                            float(metric_obj.value), str(unit_str), str(fp), int(fy) if fy else None,
                            filing_ts, "polygon_rest", ingest_ts))
        if rows:
            df = spark.createDataFrame(rows, schema=econ_schema)
            df.write.format("delta").mode("append").saveAsTable(f"{CATALOG_SCHEMA}.bronze_economic_metrics")
            fin_total += len(rows)
        print(f"  [{i:2d}/{len(TICKERS)}] {ticker:<6} {len(fins):>3} filings → {len(rows):>6,} metrics  (cum: {fin_total:>9,})")
    except Exception as e:
        print(f"  [{i:2d}/{len(TICKERS)}] {ticker:<6} {str(e)[:100]}")
    time.sleep(0.15)
print(f"  ✓ Financials: {fin_total:,} rows")

# A4b: Forex + Crypto + Index daily bars
print("\n  ── Forex / Crypto / Index bars ──")
MACRO_TICKERS = {
    "C:EURUSD": ("forex", "ratio"), "C:USDJPY": ("forex", "ratio"),
    "C:GBPUSD": ("forex", "ratio"), "C:USDCHF": ("forex", "ratio"),
    "C:AUDUSD": ("forex", "ratio"),
    "X:BTCUSD": ("crypto", "USD"), "X:ETHUSD": ("crypto", "USD"),
    "X:SOLUSD": ("crypto", "USD"),
    "I:NDX":    ("index", "index_points"),
}
macro_total = 0
for ticker, (mtype, unit) in MACRO_TICKERS.items():
    try:
        aggs = list(client.get_aggs(ticker, 1, "day", "2020-01-01", to_date, adjusted=True, limit=50000))
        rows = []
        for a in aggs:
            ts = datetime.fromtimestamp(a.timestamp / 1000, tz=timezone.utc) if a.timestamp else None
            for metric, val in [("open", a.open), ("high", a.high), ("low", a.low),
                                ("close", a.close), ("volume", a.volume), ("vwap", a.vwap)]:
                if val is not None:
                    rows.append((mtype, ticker, metric, float(val), unit,
                        ts.strftime("%Y-%m-%d") if ts else None, ts.year if ts else None,
                        ts, "polygon_rest", ingest_ts))
        if rows:
            df = spark.createDataFrame(rows, schema=econ_schema)
            df.write.format("delta").mode("append").saveAsTable(f"{CATALOG_SCHEMA}.bronze_economic_metrics")
            macro_total += len(rows)
        print(f"  ✓ {ticker:<12} {len(aggs):>5,} bars → {len(rows):>7,} metrics")
    except Exception as e:
        print(f"  ✗ {ticker:<12} {str(e)[:80]}")
    time.sleep(0.2)
print(f"  ✓ Macro data: {macro_total:,} rows")

print("\n" + "="*70)
print(f"  OPTION A COMPLETE")
print(f"  Stock minute: {grand_total:,} | Stock day: {grand_total_day:,}")
print(f"  Options: {options_total:,} | Financials: {fin_total:,} | Macro: {macro_total:,}")
print("="*70)

# COMMAND ----------

# DBTITLE 1,OPTION B: Flat Files (S3) — ENTIRE MARKET minute + day bars
# Massive Flat Files -> Databricks Delta (safer capstone ingestion)
#
# Fixes vs original:
# - Streams gzip rows instead of reading/decompressing whole files into driver RAM
# - Batches Spark writes
# - Adds source_file for lineage
# - Uses an ingestion log for idempotency / restart safety
# - Does not silently swallow S3 errors
# - Keeps options aggregates separate from trades
# - Defaults to stock minute bars only (enough for >1M rows in most capstone setups)

import boto3
import csv
import gzip
import io
from datetime import datetime, timezone
from botocore.config import Config
from pyspark.sql import SparkSession
from pyspark.sql.types import (
    StructType, StructField, StringType, TimestampType, DoubleType,
    LongType, IntegerType
)

# -----------------------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------------------
CATALOG_SCHEMA = "bootcamp_students.evangoh_capstone"
BUCKET = "flatfiles"
ENDPOINT = "https://files.massive.com"

START_YEAR = 2022
END_YEAR = 2026

# Full market: minute + day bars for all US stocks
DATASETS = [
    ("us_stocks_sip/minute_aggs_v1", "minute"),
    ("us_stocks_sip/day_aggs_v1", "day"),
]

# Batch size controls Python memory usage before each Spark write.
BATCH_SIZE = 50_000

# ENTIRE MARKET: empty set disables filtering — all US stocks included.
# Each daily file has ~10K+ symbols, expect 500K-1M+ rows per file.
# 2022-2026 = ~1,000 trading days × ~700K rows/day = ~700M+ total rows.
TICKERS = [
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "NVDA", "META", "TSLA",
    "AMD", "INTC", "QCOM", "AVGO", "TXN", "MRVL", "MU", "SNDK",
    "AMAT", "LRCX", "KLAC", "ASML", "TSM", "ON", "MPWR",
    "NXPI", "ADI", "MCHP", "SWKS", "QRVO", "ENTG", "CRUS",
    "WOLF", "ONTO", "ACLS", "SLAB", "STM",
    "SPY", "QQQ", "IWM", "DIA", "XLF", "XLK", "XLE",
    "JPM", "GS", "BAC", "MS",
    "NFLX", "CRM", "UBER", "COIN", "XOM", "JNJ", "V", "WMT",
]
print(f"\nTicker universe: {len(TICKERS)} symbols")

BRONZE_TABLE = f"{CATALOG_SCHEMA}.bronze_ohlcv"
INGEST_LOG_TABLE = f"{CATALOG_SCHEMA}.massive_ingestion_log"

spark = SparkSession.builder.getOrCreate()

# -----------------------------------------------------------------------------
# SECRETS + MASSIVE S3 CLIENT
# -----------------------------------------------------------------------------
try:
    access_key = dbutils.secrets.get(
        scope="evangoh_capstone", key="massive_s3_access_key"
    )
    secret_key = dbutils.secrets.get(
        scope="evangoh_capstone", key="massive_s3_secret_key"
    )
except Exception as e:
    raise RuntimeError(
        "Massive Flat Files credentials were not found in Databricks secret scope "
        "'evangoh_capstone'. Expected keys: massive_s3_access_key and "
        "massive_s3_secret_key."
    ) from e

s3 = boto3.client(
    "s3",
    endpoint_url=ENDPOINT,
    aws_access_key_id=access_key,
    aws_secret_access_key=secret_key,
    region_name="us-east-1",
    config=Config(signature_version="s3v4"),
)

# -----------------------------------------------------------------------------
# TABLES
# -----------------------------------------------------------------------------
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG_SCHEMA}")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {INGEST_LOG_TABLE} (
    source_file STRING,
    dataset STRING,
    status STRING,
    row_count BIGINT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message STRING
)
USING DELTA
""")

ohlcv_schema = StructType([
    StructField("symbol", StringType(), False),
    StructField("event_ts", TimestampType(), True),
    StructField("open", DoubleType(), True),
    StructField("high", DoubleType(), True),
    StructField("low", DoubleType(), True),
    StructField("close", DoubleType(), True),
    StructField("volume", LongType(), True),
    StructField("vwap", DoubleType(), True),
    StructField("trade_count", IntegerType(), True),
    StructField("timespan", StringType(), False),
    StructField("source", StringType(), False),
    StructField("raw_payload", StringType(), True),
    StructField("source_file", StringType(), True),
    StructField("ingest_ts", TimestampType(), False),
])

# Create empty Bronze table once with the desired schema.
if not spark.catalog.tableExists(BRONZE_TABLE):
    spark.createDataFrame([], schema=ohlcv_schema) \
        .write.format("delta").mode("overwrite").saveAsTable(BRONZE_TABLE)

# -----------------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------------
def sql_escape(value: str) -> str:
    return value.replace("'", "''")


def already_ingested(source_file: str) -> bool:
    safe = sql_escape(source_file)
    return spark.sql(f"""
        SELECT 1
        FROM {INGEST_LOG_TABLE}
        WHERE source_file = '{safe}' AND status = 'SUCCESS'
        LIMIT 1
    """).count() > 0


def log_start(source_file: str, dataset: str):
    now = datetime.now(timezone.utc)
    spark.createDataFrame(
        [(source_file, dataset, "RUNNING", 0, now, None, None)],
        "source_file string, dataset string, status string, row_count long, "
        "started_at timestamp, completed_at timestamp, error_message string",
    ).write.format("delta").mode("append").saveAsTable(INGEST_LOG_TABLE)


def log_finish(source_file: str, row_count: int, error_message=None):
    safe = sql_escape(source_file)
    now = datetime.now(timezone.utc).isoformat()
    if error_message is None:
        spark.sql(f"""
            UPDATE {INGEST_LOG_TABLE}
            SET status = 'SUCCESS',
                row_count = {int(row_count)},
                completed_at = TIMESTAMP('{now}'),
                error_message = NULL
            WHERE source_file = '{safe}' AND status = 'RUNNING'
        """)
    else:
        err = sql_escape(str(error_message)[:4000])
        spark.sql(f"""
            UPDATE {INGEST_LOG_TABLE}
            SET status = 'FAILED',
                row_count = {int(row_count)},
                completed_at = TIMESTAMP('{now}'),
                error_message = '{err}'
            WHERE source_file = '{safe}' AND status = 'RUNNING'
        """)


def list_s3_files(prefix: str):
    """List .csv.gz files only in the requested year range."""
    files = []
    paginator = s3.get_paginator("list_objects_v2")

    for year in range(START_YEAR, END_YEAR + 1):
        year_prefix = f"{prefix}/{year}/"
        try:
            for page in paginator.paginate(Bucket=BUCKET, Prefix=year_prefix):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    if key.endswith(".csv.gz"):
                        files.append((key, obj["Size"]))
        except Exception as e:
            # Skip years/prefixes that return 403 (not authorized)
            if "403" in str(e) or "Forbidden" in str(e):
                print(f"  ⚠ Skipping {year_prefix} (not authorized)")
                continue
            raise RuntimeError(
                f"Failed listing Massive files under {year_prefix}: {e}"
            ) from e

    # Massive filenames are date based, so lexical sorting is chronological.
    return sorted(files, key=lambda x: x[0])


def ns_to_ts(value):
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1_000_000_000, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def as_float(row, key):
    value = row.get(key)
    return float(value) if value not in (None, "") else None


def as_int(row, key):
    value = row.get(key)
    return int(float(value)) if value not in (None, "") else None


def write_batch(rows):
    if not rows:
        return
    df = spark.createDataFrame(rows, schema=ohlcv_schema)
    (
        df.write.format("delta")
        .mode("append")
        .option("mergeSchema", "true")
        .saveAsTable(BRONZE_TABLE)
    )


def ingest_stock_aggregate_file(key: str, timespan: str) -> int:
    """
    Stream one Massive gzip CSV directly from the response body.

    Important: this avoids resp['Body'].read(), gzip.decompress(...), and
    list(reader), which were the major driver-memory issues in the original.
    """
    ingest_ts = datetime.now(timezone.utc)
    response = s3.get_object(Bucket=BUCKET, Key=key)

    # StreamingBody -> GzipFile -> TextIOWrapper -> DictReader
    with gzip.GzipFile(fileobj=response["Body"], mode="rb") as gz:
        with io.TextIOWrapper(gz, encoding="utf-8", newline="") as text_stream:
            reader = csv.DictReader(text_stream)

            rows = []
            written = 0

            for r in reader:
                ticker = r.get("ticker", "")
                if TICKERS and ticker not in TICKERS:
                    continue

                # Massive aggregate flat files use window_start for bar time.
                event_ts = ns_to_ts(r.get("window_start"))

                rows.append((
                    ticker,
                    event_ts,
                    as_float(r, "open"),
                    as_float(r, "high"),
                    as_float(r, "low"),
                    as_float(r, "close"),
                    as_int(r, "volume"),
                    # Some aggregate flat-file variants may not include vwap.
                    as_float(r, "vwap"),
                    as_int(r, "transactions"),
                    timespan,
                    "massive_flatfile",
                    None,  # raw_payload (matches existing table column)
                    key,   # source_file (new column for lineage)
                    ingest_ts,
                ))

                if len(rows) >= BATCH_SIZE:
                    write_batch(rows)
                    written += len(rows)
                    rows.clear()

            if rows:
                write_batch(rows)
                written += len(rows)

    return written


# -----------------------------------------------------------------------------
# ACCESS PROBE
# -----------------------------------------------------------------------------
print("Probing Massive Flat Files access...")
probe_prefix = "us_stocks_sip/minute_aggs_v1/2025/"
try:
    probe = s3.list_objects_v2(Bucket=BUCKET, Prefix=probe_prefix, MaxKeys=1)
    if not probe.get("Contents"):
        raise RuntimeError(
            f"Connected to Massive, but no objects were visible under {probe_prefix}. "
            "Check your plan entitlement / history window."
        )
    print(f"✓ Massive S3 access works. Example object: {probe['Contents'][0]['Key']}")
except Exception as e:
    raise RuntimeError(
        "Massive Flat Files access probe failed. Check that your subscription includes "
        "Flat Files and that the S3 access/secret keys are correct."
    ) from e


# -----------------------------------------------------------------------------
# INGEST
# -----------------------------------------------------------------------------
print(f"Ticker universe: {len(TICKERS)} symbols")
print(f"Target Bronze table: {BRONZE_TABLE}")

for prefix, timespan in DATASETS:
    print("\n" + "=" * 80)
    print(f"DATASET: {prefix} ({timespan})")
    print("=" * 80)

    files = list_s3_files(prefix)
    print(f"Found {len(files):,} candidate files for {START_YEAR}-{END_YEAR}")

    dataset_total = 0
    skipped = 0
    failed = 0

    for i, (key, size_bytes) in enumerate(files, 1):
        if already_ingested(key):
            skipped += 1
            continue

        log_start(key, prefix)
        rows_written = 0

        try:
            rows_written = ingest_stock_aggregate_file(key, timespan)
            log_finish(key, rows_written)
            dataset_total += rows_written

            print(
                f"[{i:>4}/{len(files)}] ✓ {key.split('/')[-1]} | "
                f"{size_bytes / (1024**2):7.1f} MB | {rows_written:>8,} rows"
            )
        except Exception as e:
            failed += 1
            log_finish(key, rows_written, error_message=e)
            print(f"[{i:>4}/{len(files)}] ✗ {key}: {e}")
            # Continue with the next day instead of losing all prior successful work.

    print(
        f"Completed {prefix}: new_rows={dataset_total:,}, "
        f"skipped_files={skipped:,}, failed_files={failed:,}"
    )


# -----------------------------------------------------------------------------
# VALIDATION
# -----------------------------------------------------------------------------
print("\nValidation")
spark.sql(f"""
SELECT
    timespan,
    COUNT(*) AS rows,
    COUNT(DISTINCT symbol) AS symbols,
    MIN(event_ts) AS min_event_ts,
    MAX(event_ts) AS max_event_ts,
    COUNT(DISTINCT source_file) AS source_files  -- will be NULL for REST-loaded rows
FROM {BRONZE_TABLE}
GROUP BY timespan
ORDER BY timespan
""").show(truncate=False)

print("\nIngestion status")
spark.sql(f"""
SELECT status, COUNT(*) AS files, SUM(row_count) AS rows
FROM {INGEST_LOG_TABLE}
GROUP BY status
ORDER BY status
""").show(truncate=False)

print("\nMASSIVE FLAT FILE INGESTION COMPLETE")

# COMMAND ----------

# DBTITLE 1,Options Market
# Massive / Polygon Options Flat Files -> Databricks Delta
#
# OPTIONS ONLY
#
# Loads:
#   us_options_opra/day_aggs_v1    -> bronze_options_day
#   us_options_opra/minute_aggs_v1 -> bronze_options_minute
#
# Design:
# - No stock OHLCV ingestion.
# - No indices / forex / crypto ingestion.
# - Separate Delta tables for day and minute option aggregates.
# - Raw path reads (s3a://, direct CSV globs) are blocked on Unity Catalog
#   shared/standard clusters by the ANY FILE securable, so instead we STAGE
#   each year's gzip CSVs into a UC Volume using the boto3 S3 client (which
#   runs in the driver and bypasses that check), then let Spark read the
#   Volume. Reads from a Volume are fully governed and need no ANY FILE grant.
# - Year-by-year: stage -> load -> clean up, so the (huge) minute dataset
#   never fully lands on the Volume at once.
# - Entitlement-tolerant: Massive/Polygon plans grant a rolling history
#   window, so objects older than the cutoff return 403 Forbidden on GET even
#   though they list fine. Staging skips forbidden files (and skips a year
#   entirely if nothing in it is fetchable) instead of hard-failing. You can
#   therefore leave START_YEAR early and just load whatever the plan allows.
# - Year-by-year writes with replaceWhere for re-run safety.
# - Parses OPRA option symbols into underlying / expiry / strike / right.
# - Stores source_file lineage.
# - Defaults to ALL option underlyings. Set FILTER_UNDERLYINGS=True to restrict.
#
# Prerequisite:
# Databricks secret scope: evangoh_capstone
# Keys:
#   massive_s3_access_key
#   massive_s3_secret_key

import os
import shutil

import boto3
import botocore
from botocore.config import Config
from datetime import datetime, timezone

from pyspark.sql import SparkSession, functions as F


# =============================================================================
# CONFIG
# =============================================================================

CATALOG = "bootcamp_students"
SCHEMA = "evangoh_capstone"
CATALOG_SCHEMA = f"{CATALOG}.{SCHEMA}"
BUCKET = "flatfiles"

# UC Volume used to stage raw gzip CSVs pulled via boto3.
VOLUME_NAME = "flatfiles_raw"
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME_NAME}"

# Delete each year's staged files after its Delta write succeeds.
# Keep True unless you have a specific reason to retain the raw CSVs.
STAGE_CLEANUP = True

ENDPOINT_CANDIDATES = [
    "files.massive.com",
    "files.polygon.io",
]

START_YEAR = 2024
END_YEAR = 2026

OPTIONS_DAY_PREFIX = "us_options_opra/day_aggs_v1"
OPTIONS_MINUTE_PREFIX = "us_options_opra/minute_aggs_v1"

BRONZE_OPTIONS_DAY = f"{CATALOG_SCHEMA}.bronze_options_day"
BRONZE_OPTIONS_MINUTE = f"{CATALOG_SCHEMA}.bronze_options_minute"

OPTIONS_DAY_YEARS = list(range(START_YEAR, END_YEAR + 1))

# WARNING:
# The entire U.S. options minute dataset is extremely large.
# For a smoke test, temporarily use:
# OPTIONS_MINUTE_YEARS = [2025]

# Default: ingest every option underlying.
FILTER_UNDERLYINGS = False

# Used only when FILTER_UNDERLYINGS=True.
UNDERLYINGS = {
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "NVDA", "META", "TSLA",
    "AMD", "INTC", "QCOM", "AVGO", "TXN", "MRVL", "MU",
    "AMAT", "LRCX", "KLAC",
    "SPY", "QQQ", "IWM", "DIA",
}

spark = SparkSession.builder.getOrCreate()
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG_SCHEMA}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG_SCHEMA}.{VOLUME_NAME}")

ingest_ts = datetime.now(timezone.utc)


# =============================================================================
# CREDENTIALS
# =============================================================================

try:
    access_key = dbutils.secrets.get(
        scope="evangoh_capstone",
        key="massive_s3_access_key",
    )
    secret_key = dbutils.secrets.get(
        scope="evangoh_capstone",
        key="massive_s3_secret_key",
    )
except Exception as e:
    raise RuntimeError(
        "Missing flat-file credentials in Databricks secret scope "
        "'evangoh_capstone'. Expected keys: "
        "'massive_s3_access_key' and 'massive_s3_secret_key'."
    ) from e


# =============================================================================
# ENDPOINT AUTO-DETECTION
# =============================================================================

def make_s3_client(host: str):
    return boto3.client(
        "s3",
        endpoint_url=f"https://{host}",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="us-east-1",
        config=Config(signature_version="s3v4"),
    )


PROBE_KEY = f"{OPTIONS_DAY_PREFIX}/2025/01/2025-01-02.csv.gz"

ENDPOINT = None
s3 = None

print("Detecting options flat-file endpoint...")

for host in ENDPOINT_CANDIDATES:
    try:
        client = make_s3_client(host)
        metadata = client.head_object(
            Bucket=BUCKET,
            Key=PROBE_KEY,
        )
        size_mb = metadata["ContentLength"] / (1024 ** 2)

        ENDPOINT = host
        s3 = client

        print(
            f"  ✓ using {host} "
            f"(probe file {size_mb:,.1f} MB compressed)"
        )
        break
    except Exception as e:
        code = (
            getattr(e, "response", {})
            .get("Error", {})
            .get("Code", type(e).__name__)
        )
        print(f"  ✗ {host}: {code}")

if ENDPOINT is None:
    raise RuntimeError(
        "Could not access the options flat-file dataset using any configured "
        "endpoint. Check your subscription entitlement and S3 credentials."
    )


# =============================================================================
# DATASET PROBES
# =============================================================================

print("\nProbing options datasets...")

probe_paths = [
    (
        f"{OPTIONS_DAY_PREFIX}/2025/01/2025-01-02.csv.gz",
        "Options day",
    ),
    (
        f"{OPTIONS_MINUTE_PREFIX}/2025/01/2025-01-02.csv.gz",
        "Options minute",
    ),
]

for key, label in probe_paths:
    try:
        metadata = s3.head_object(
            Bucket=BUCKET,
            Key=key,
        )
        size_mb = metadata["ContentLength"] / (1024 ** 2)
        print(
            f"  ✓ {label:<15} "
            f"{size_mb:>10,.1f} MB compressed"
        )
    except Exception as e:
        code = (
            getattr(e, "response", {})
            .get("Error", {})
            .get("Code", type(e).__name__)
        )
        raise RuntimeError(
            f"Cannot access {label} flat files. "
            f"Probe failed with code={code}: {e}"
        ) from e


# =============================================================================
# OPTION SYMBOL PARSING
# =============================================================================

# Example:
# O:AAPL250117C00200000
#
# O:        prefix
# AAPL      underlying
# 250117    expiry YYMMDD
# C         C/P
# 00200000  strike * 1000 = 200.000

OPRA_REGEX = r"^O:(.+?)(\d{6})([CP])(\d{8})$"


# =============================================================================
# STAGING (boto3 -> UC Volume)
# =============================================================================

def year_path(prefix: str, year: int) -> str:
    # Spark reads the STAGED copy in the Volume, not the remote endpoint.
    # Layout mirrors the source: <prefix>/<year>/<month>/<date>.csv.gz
    return f"{VOLUME_PATH}/{prefix}/{year}/*/*.csv.gz"


_FORBIDDEN_CODES = ("403", "AccessDenied", "Forbidden")


def stage_year(prefix: str, year: int) -> int:
    """Download a prefix/year's gzip CSVs into the UC Volume.

    Runs in the driver via the boto3 client, so it is not subject to the
    ANY FILE check that blocks Spark raw-path reads on shared clusters.

    Objects outside the plan's rolling history window return 403 on GET even
    though they list fine, so per-object 403s are skipped rather than fatal.
    Returns the number of files actually staged (0 => nothing entitled).
    """
    base = f"{prefix}/{year}/"
    paginator = s3.get_paginator("list_objects_v2")

    n_files = 0
    n_forbidden = 0
    n_listed = 0
    total_bytes = 0

    for page in paginator.paginate(Bucket=BUCKET, Prefix=base):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(".csv.gz"):
                continue

            n_listed += 1
            dst = f"{VOLUME_PATH}/{key}"
            os.makedirs(os.path.dirname(dst), exist_ok=True)

            # Skip re-download if already staged (re-run friendly).
            if not os.path.exists(dst):
                try:
                    s3.download_file(BUCKET, key, dst)
                except botocore.exceptions.ClientError as e:
                    code = e.response.get("Error", {}).get("Code")
                    if code in _FORBIDDEN_CODES:
                        n_forbidden += 1
                        continue  # outside entitlement window; skip this file
                    raise

            n_files += 1
            total_bytes += obj.get("Size", 0)

    if n_listed == 0:
        print(f"  ⚠ no .csv.gz listed for {prefix}/{year}; skipping year")
        return 0

    if n_forbidden:
        print(
            f"  skipped {n_forbidden} forbidden files "
            f"(outside entitlement window)"
        )

    if n_files == 0:
        print(
            f"  ⚠ nothing entitled for {prefix}/{year} "
            f"({n_listed} files listed, all forbidden); skipping year"
        )
        return 0

    print(
        f"  staged {n_files} files "
        f"({total_bytes / (1024 ** 3):,.2f} GB compressed) for {year}"
    )
    return n_files


def clear_staged(prefix: str, year: int):
    year_dir = f"{VOLUME_PATH}/{prefix}/{year}"
    if os.path.isdir(year_dir):
        shutil.rmtree(year_dir)
        print(f"  cleaned staged files for {year}")


# =============================================================================
# HELPERS
# =============================================================================

def read_option_aggs(prefix: str, year: int):
    return (
        spark.read
        .option("header", True)
        .csv(year_path(prefix, year))
    )


def shape_options(prefix: str, year: int, timespan: str):
    raw = read_option_aggs(prefix, year)

    event_ts = (
        F.col("window_start").cast("double")
        / F.lit(1_000_000_000.0)
    ).cast("timestamp")

    df = (
        raw
        .withColumn(
            "underlying",
            F.regexp_extract("ticker", OPRA_REGEX, 1),
        )
        .withColumn(
            "expiry_raw",
            F.regexp_extract("ticker", OPRA_REGEX, 2),
        )
        .withColumn(
            "right_raw",
            F.regexp_extract("ticker", OPRA_REGEX, 3),
        )
        .withColumn(
            "strike_raw",
            F.regexp_extract("ticker", OPRA_REGEX, 4),
        )
        .withColumn("event_ts", event_ts)
    )

    df = df.filter(
        (F.col("underlying") != "")
        & (F.col("expiry_raw") != "")
        & (F.col("right_raw") != "")
        & (F.col("strike_raw") != "")
        & F.col("event_ts").isNotNull()
    )

    if FILTER_UNDERLYINGS:
        df = df.filter(
            F.col("underlying").isin(list(UNDERLYINGS))
        )

    return (
        df.select(
            F.col("ticker").alias("contract_symbol"),
            F.col("underlying"),

            F.to_date(
                F.col("expiry_raw"),
                "yyMMdd",
            ).alias("expiry"),

            (
                F.col("strike_raw").cast("double")
                / F.lit(1000.0)
            ).alias("strike"),

            F.when(
                F.col("right_raw") == "C",
                F.lit("CALL"),
            )
            .when(
                F.col("right_raw") == "P",
                F.lit("PUT"),
            )
            .otherwise(F.lit(None).cast("string"))
            .alias("right"),

            F.col("event_ts"),
            F.to_date("event_ts").alias("event_date"),
            F.year("event_ts").alias("event_year"),

            F.col("open").cast("double").alias("open"),
            F.col("high").cast("double").alias("high"),
            F.col("low").cast("double").alias("low"),
            F.col("close").cast("double").alias("close"),
            F.col("volume").cast("long").alias("volume"),
            F.col("transactions").cast("long").alias("trade_count"),

            F.lit(timespan).alias("timespan"),
            F.lit("massive_flatfile").alias("source"),
            F.col("_metadata.file_path").alias("source_file"),
            F.lit(ingest_ts).alias("ingest_ts"),
        )
    )


def ensure_delta_table(df, table_name: str):
    if not spark.catalog.tableExists(table_name):
        (
            spark.createDataFrame([], df.schema)
            .write
            .format("delta")
            .mode("overwrite")
            .saveAsTable(table_name)
        )


def validate_year(df, year: int, label: str):
    bad_year = (
        df.filter(F.col("event_year") != F.lit(year))
        .limit(1)
        .count()
    )

    if bad_year:
        raise RuntimeError(
            f"{label} {year}: rows found outside expected year."
        )


def write_year(
    prefix: str,
    table_name: str,
    year: int,
    timespan: str,
):
    print(
        f"\nLoading {timespan.upper():<6} "
        f"{year} -> {table_name}"
    )

    # 1. Stage raw CSVs into the Volume (boto3, bypasses ANY FILE check).
    #    Returns 0 when the whole year is outside the entitlement window.
    n_staged = stage_year(prefix=prefix, year=year)
    if n_staged == 0:
        print(f"  ↳ skipped {timespan} {year}: not entitled / no data")
        return

    try:
        # 2. Shape from the staged Volume copy.
        df = shape_options(
            prefix=prefix,
            year=year,
            timespan=timespan,
        )

        # 3. Guard against stray rows from adjacent years.
        validate_year(
            df=df,
            year=year,
            label=timespan,
        )

        # 4. Create the table on first run.
        ensure_delta_table(
            df=df,
            table_name=table_name,
        )

        # 5. Idempotent per-year write.
        (
            df.write
            .format("delta")
            .mode("overwrite")
            .option(
                "replaceWhere",
                f"event_year = {year}",
            )
            .saveAsTable(table_name)
        )
    finally:
        # 6. Reclaim Volume space regardless of outcome.
        if STAGE_CLEANUP:
            clear_staged(prefix=prefix, year=year)

    print(f"  ✓ completed {timespan} {year}")


# =============================================================================
# LOAD DAY OPTIONS
# =============================================================================

print("\n" + "=" * 80)
print("OPTIONS DAY AGGREGATES")
print("=" * 80)

for year in OPTIONS_DAY_YEARS:
    try:
        write_year(
            prefix=OPTIONS_DAY_PREFIX,
            table_name=BRONZE_OPTIONS_DAY,
            year=year,
            timespan="day",
        )
    except Exception as e:
        raise RuntimeError(
            f"Options DAY ingestion failed for {year}: {e}"
        ) from e

# =============================================================================
# VALIDATION
# =============================================================================

print("\n" + "=" * 80)
print("OPTIONS INGESTION VALIDATION")
print("=" * 80)

for table_name in [
    BRONZE_OPTIONS_DAY,
]:
    print(f"\n{table_name}")

    (
        spark.table(table_name)
        .groupBy(
            "timespan",
            "event_year",
        )
        .agg(
            F.count("*").alias("rows"),
            F.countDistinct("contract_symbol").alias("contracts"),
            F.countDistinct("underlying").alias("underlyings"),
            F.min("event_ts").alias("min_event_ts"),
            F.max("event_ts").alias("max_event_ts"),
            F.countDistinct("source_file").alias("source_files"),
        )
        .orderBy("event_year")
        .show(truncate=False)
    )


# =============================================================================
# OPTIONAL OPTIMIZATION COMMANDS
# =============================================================================

print("\n" + "=" * 80)
print("OPTIONS LOAD COMPLETE")
print("=" * 80)

print("\nTables created:")
print(f"  {BRONZE_OPTIONS_DAY}")
print(f"  {BRONZE_OPTIONS_MINUTE}")

print(
    "\nUnderlying filter: "
    + (
        f"{len(UNDERLYINGS)} configured underlyings"
        if FILTER_UNDERLYINGS
        else "ALL option contracts"
    )
)

print("\nRecommended after the initial load:")

print(
    f"""
ALTER TABLE {BRONZE_OPTIONS_DAY}
CLUSTER BY (underlying, event_date);

OPTIMIZE {BRONZE_OPTIONS_DAY};
"""
)


# COMMAND ----------

# DBTITLE 1,Entire Market OHLCV daily
# Massive Flat Files -> Databricks Delta
# FULL U.S. STOCK MARKET DAILY OHLCV ONLY
#
# Loads:
#   us_stocks_sip/day_aggs_v1
#       -> bootcamp_students.evangoh_capstone.bronze_ohlcv_day
#
# Design:
# - Daily aggregates only. No minute ingestion.
# - Full market: no ticker filter.
# - Streams gzip CSV files directly from Massive S3-compatible flat-file storage.
# - Writes to Delta in batches.
# - Maintains a per-file ingestion log for idempotent reruns.
# - Skips files outside the subscription entitlement window when Massive returns 403.
# - Keeps source_file lineage using the Massive object key.
#
# Databricks secret scope required:
#   scope: evangoh_capstone
#   keys:
#       massive_s3_access_key
#       massive_s3_secret_key

import csv
import gzip
import io
from datetime import datetime, timezone

import boto3
import botocore
from botocore.config import Config
from pyspark.sql import SparkSession
from pyspark.sql.types import (
    StructType,
    StructField,
    StringType,
    TimestampType,
    DateType,
    DoubleType,
    LongType,
    IntegerType,
)


# =============================================================================
# CONFIG
# =============================================================================

CATALOG = "bootcamp_students"
SCHEMA = "evangoh_capstone"
CATALOG_SCHEMA = f"{CATALOG}.{SCHEMA}"

BUCKET = "flatfiles"

ENDPOINT_CANDIDATES = [
    "files.massive.com",
    "files.polygon.io",
]

# Adjust as needed.
START_YEAR = 2022
END_YEAR = 2026

# Massive full-market U.S. stock daily aggregates.
DAY_PREFIX = "us_stocks_sip/day_aggs_v1"

# Separate daily table. Minute data lives elsewhere and is not touched here.
BRONZE_DAY_TABLE = f"{CATALOG_SCHEMA}.bronze_ohlcv_day"

# File-level ingestion state.
INGEST_LOG_TABLE = f"{CATALOG_SCHEMA}.massive_daily_ingestion_log"

# Number of parsed rows held in Python before each Spark append.
BATCH_SIZE = 50_000


# =============================================================================
# SPARK / UNITY CATALOG SETUP
# =============================================================================

spark = SparkSession.builder.getOrCreate()

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG_SCHEMA}")


# =============================================================================
# MASSIVE CREDENTIALS
# =============================================================================

try:
    access_key = dbutils.secrets.get(
        scope="evangoh_capstone",
        key="massive_s3_access_key",
    )
    secret_key = dbutils.secrets.get(
        scope="evangoh_capstone",
        key="massive_s3_secret_key",
    )
except Exception as e:
    raise RuntimeError(
        "Missing Massive flat-file credentials in Databricks secret scope "
        "'evangoh_capstone'. Expected keys: "
        "'massive_s3_access_key' and 'massive_s3_secret_key'."
    ) from e


# =============================================================================
# MASSIVE ENDPOINT AUTO-DETECTION
# =============================================================================

def make_s3_client(host: str):
    return boto3.client(
        "s3",
        endpoint_url=f"https://{host}",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="us-east-1",
        config=Config(signature_version="s3v4"),
    )


# Probe a known daily aggregate path.
PROBE_KEY = f"{DAY_PREFIX}/2025/01/2025-01-02.csv.gz"

ENDPOINT = None
s3 = None

print("Detecting Massive flat-file endpoint...")

for host in ENDPOINT_CANDIDATES:
    try:
        client = make_s3_client(host)
        metadata = client.head_object(
            Bucket=BUCKET,
            Key=PROBE_KEY,
        )

        size_mb = metadata["ContentLength"] / (1024 ** 2)

        ENDPOINT = host
        s3 = client

        print(
            f"  ✓ using {host} "
            f"(probe file {size_mb:,.1f} MB compressed)"
        )
        break

    except Exception as e:
        code = (
            getattr(e, "response", {})
            .get("Error", {})
            .get("Code", type(e).__name__)
        )
        print(f"  ✗ {host}: {code}")


if ENDPOINT is None:
    raise RuntimeError(
        "Could not access Massive daily stock flat files through any configured "
        "endpoint. Check your subscription entitlement and S3 credentials."
    )


# =============================================================================
# TABLE SCHEMAS
# =============================================================================

ohlcv_schema = StructType([
    StructField("symbol", StringType(), False),

    # Timestamp supplied by Massive.
    StructField("event_ts", TimestampType(), True),

    # Convenient daily dimensions for downstream queries.
    StructField("event_date", DateType(), True),
    StructField("event_year", IntegerType(), True),

    StructField("open", DoubleType(), True),
    StructField("high", DoubleType(), True),
    StructField("low", DoubleType(), True),
    StructField("close", DoubleType(), True),
    StructField("volume", LongType(), True),
    StructField("vwap", DoubleType(), True),
    StructField("trade_count", LongType(), True),

    StructField("timespan", StringType(), False),
    StructField("source", StringType(), False),

    # Massive object key, e.g.
    # us_stocks_sip/day_aggs_v1/2025/01/2025-01-02.csv.gz
    StructField("source_file", StringType(), True),

    StructField("ingest_ts", TimestampType(), False),
])


# Create daily Bronze table if needed.
if not spark.catalog.tableExists(BRONZE_DAY_TABLE):
    (
        spark.createDataFrame([], schema=ohlcv_schema)
        .write
        .format("delta")
        .mode("overwrite")
        .saveAsTable(BRONZE_DAY_TABLE)
    )


spark.sql(f"""
CREATE TABLE IF NOT EXISTS {INGEST_LOG_TABLE} (
    source_file STRING,
    dataset STRING,
    status STRING,
    row_count BIGINT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message STRING
)
USING DELTA
""")


# =============================================================================
# HELPERS
# =============================================================================

def sql_escape(value: str) -> str:
    return value.replace("'", "''")


def ns_to_ts(value):
    """Convert Massive nanosecond Unix timestamp to timezone-aware datetime."""
    if value in (None, ""):
        return None

    try:
        return datetime.fromtimestamp(
            int(value) / 1_000_000_000,
            tz=timezone.utc,
        )
    except (TypeError, ValueError, OverflowError):
        return None


def as_float(row, key):
    value = row.get(key)
    return float(value) if value not in (None, "") else None


def as_int(row, key):
    value = row.get(key)
    return int(float(value)) if value not in (None, "") else None


def already_ingested(source_file: str) -> bool:
    safe = sql_escape(source_file)

    return (
        spark.sql(f"""
            SELECT 1
            FROM {INGEST_LOG_TABLE}
            WHERE source_file = '{safe}'
              AND status = 'SUCCESS'
            LIMIT 1
        """)
        .count()
        > 0
    )


def log_start(source_file: str):
    now = datetime.now(timezone.utc)

    spark.createDataFrame(
        [
            (
                source_file,
                DAY_PREFIX,
                "RUNNING",
                0,
                now,
                None,
                None,
            )
        ],
        """
        source_file string,
        dataset string,
        status string,
        row_count long,
        started_at timestamp,
        completed_at timestamp,
        error_message string
        """,
    ).write.format("delta").mode("append").saveAsTable(INGEST_LOG_TABLE)


def log_finish(source_file: str, row_count: int, error_message=None):
    safe = sql_escape(source_file)
    now = datetime.now(timezone.utc).isoformat()

    if error_message is None:
        spark.sql(f"""
            UPDATE {INGEST_LOG_TABLE}
            SET status = 'SUCCESS',
                row_count = {int(row_count)},
                completed_at = TIMESTAMP('{now}'),
                error_message = NULL
            WHERE source_file = '{safe}'
              AND status = 'RUNNING'
        """)
    else:
        err = sql_escape(str(error_message)[:4000])

        spark.sql(f"""
            UPDATE {INGEST_LOG_TABLE}
            SET status = 'FAILED',
                row_count = {int(row_count)},
                completed_at = TIMESTAMP('{now}'),
                error_message = '{err}'
            WHERE source_file = '{safe}'
              AND status = 'RUNNING'
        """)


def list_daily_files():
    """
    List Massive daily stock aggregate .csv.gz files for START_YEAR..END_YEAR.

    Listing can expose files outside the subscription's actual GET entitlement,
    so GET-level 403s are handled again during ingestion.
    """
    files = []
    paginator = s3.get_paginator("list_objects_v2")

    for year in range(START_YEAR, END_YEAR + 1):
        year_prefix = f"{DAY_PREFIX}/{year}/"

        try:
            for page in paginator.paginate(
                Bucket=BUCKET,
                Prefix=year_prefix,
            ):
                for obj in page.get("Contents", []):
                    key = obj["Key"]

                    if key.endswith(".csv.gz"):
                        files.append(
                            (
                                key,
                                obj.get("Size", 0),
                            )
                        )

        except botocore.exceptions.ClientError as e:
            code = e.response.get("Error", {}).get("Code")

            if code in ("403", "AccessDenied", "Forbidden"):
                print(
                    f"  ⚠ skipping {year_prefix}: "
                    "not authorized by current entitlement"
                )
                continue

            raise

    # Date-based object names sort chronologically.
    return sorted(files, key=lambda x: x[0])


def write_batch(rows):
    if not rows:
        return

    df = spark.createDataFrame(rows, schema=ohlcv_schema)

    (
        df.write
        .format("delta")
        .mode("append")
        .saveAsTable(BRONZE_DAY_TABLE)
    )


# =============================================================================
# INGEST ONE DAILY FILE
# =============================================================================

def ingest_daily_file(key: str) -> int:
    """
    Stream one Massive daily aggregate gzip CSV and append all symbols.

    No ticker filtering is performed: this is full-market daily OHLCV.
    """
    ingest_ts = datetime.now(timezone.utc)

    try:
        response = s3.get_object(
            Bucket=BUCKET,
            Key=key,
        )

    except botocore.exceptions.ClientError as e:
        code = e.response.get("Error", {}).get("Code")

        if code in ("403", "AccessDenied", "Forbidden"):
            raise PermissionError(
                f"Outside Massive entitlement window: {key}"
            ) from e

        raise

    rows = []
    written = 0

    # StreamingBody -> gzip -> text -> CSV rows.
    with gzip.GzipFile(
        fileobj=response["Body"],
        mode="rb",
    ) as gz:

        with io.TextIOWrapper(
            gz,
            encoding="utf-8",
            newline="",
        ) as text_stream:

            reader = csv.DictReader(text_stream)

            for r in reader:
                symbol = r.get("ticker", "")

                if not symbol:
                    continue

                event_ts = ns_to_ts(r.get("window_start"))

                if event_ts is None:
                    continue

                event_date = event_ts.date()
                event_year = event_ts.year

                rows.append(
                    (
                        symbol,
                        event_ts,
                        event_date,
                        event_year,
                        as_float(r, "open"),
                        as_float(r, "high"),
                        as_float(r, "low"),
                        as_float(r, "close"),
                        as_int(r, "volume"),
                        as_float(r, "vwap"),
                        as_int(r, "transactions"),
                        "day",
                        "massive_flatfile",
                        key,
                        ingest_ts,
                    )
                )

                if len(rows) >= BATCH_SIZE:
                    write_batch(rows)
                    written += len(rows)
                    rows.clear()

            if rows:
                write_batch(rows)
                written += len(rows)

    return written


# =============================================================================
# INGEST FULL-MARKET DAILY OHLCV
# =============================================================================

print("\n" + "=" * 80)
print("MASSIVE FULL-MARKET DAILY OHLCV")
print("=" * 80)

print(f"Source prefix : {DAY_PREFIX}")
print(f"Target table  : {BRONZE_DAY_TABLE}")
print(f"Years         : {START_YEAR}-{END_YEAR}")
print("Ticker filter : NONE (entire market)")


files = list_daily_files()

print(f"\nFound {len(files):,} candidate daily files.")


dataset_total = 0
already_done = 0
forbidden = 0
failed = 0


for i, (key, size_bytes) in enumerate(files, 1):

    # Idempotency: don't append successful source files twice.
    if already_ingested(key):
        already_done += 1
        continue

    log_start(key)

    rows_written = 0

    try:
        rows_written = ingest_daily_file(key)

        log_finish(
            source_file=key,
            row_count=rows_written,
        )

        dataset_total += rows_written

        print(
            f"[{i:>4}/{len(files)}] ✓ "
            f"{key.split('/')[-1]} | "
            f"{size_bytes / (1024 ** 2):7.1f} MB | "
            f"{rows_written:>8,} rows"
        )

    except PermissionError as e:
        forbidden += 1

        log_finish(
            source_file=key,
            row_count=rows_written,
            error_message=e,
        )

        print(
            f"[{i:>4}/{len(files)}] ↳ "
            f"{key.split('/')[-1]} | outside entitlement window"
        )

    except Exception as e:
        failed += 1

        log_finish(
            source_file=key,
            row_count=rows_written,
            error_message=e,
        )

        print(
            f"[{i:>4}/{len(files)}] ✗ "
            f"{key} | {type(e).__name__}: {e}"
        )


print("\n" + "=" * 80)
print("INGESTION SUMMARY")
print("=" * 80)

print(f"New rows written      : {dataset_total:,}")
print(f"Already-loaded files  : {already_done:,}")
print(f"Forbidden files       : {forbidden:,}")
print(f"Failed files          : {failed:,}")


# =============================================================================
# VALIDATION
# =============================================================================

print("\n" + "=" * 80)
print("DAILY OHLCV VALIDATION")
print("=" * 80)

spark.sql(f"""
SELECT
    event_year,
    COUNT(*) AS rows,
    COUNT(DISTINCT symbol) AS symbols,
    MIN(event_date) AS min_event_date,
    MAX(event_date) AS max_event_date,
    COUNT(DISTINCT source_file) AS source_files
FROM {BRONZE_DAY_TABLE}
GROUP BY event_year
ORDER BY event_year
""").show(truncate=False)


print("\nOverall:")

spark.sql(f"""
SELECT
    COUNT(*) AS rows,
    COUNT(DISTINCT symbol) AS symbols,
    MIN(event_date) AS min_event_date,
    MAX(event_date) AS max_event_date,
    COUNT(DISTINCT source_file) AS source_files
FROM {BRONZE_DAY_TABLE}
""").show(truncate=False)


print("\nIngestion log:")

spark.sql(f"""
SELECT
    status,
    COUNT(*) AS files,
    SUM(row_count) AS rows
FROM {INGEST_LOG_TABLE}
GROUP BY status
ORDER BY status
""").show(truncate=False)


# =============================================================================
# OPTIONAL POST-LOAD OPTIMIZATION
# =============================================================================

print("\n" + "=" * 80)
print("DAILY OHLCV LOAD COMPLETE")
print("=" * 80)

print(f"\nTable: {BRONZE_DAY_TABLE}")

print(
    f"""
Recommended after the initial historical load:

ALTER TABLE {BRONZE_DAY_TABLE}
CLUSTER BY (symbol, event_date);

OPTIMIZE {BRONZE_DAY_TABLE};
"""
)

# COMMAND ----------

# DBTITLE 1,CFTC Data
# CFTC Traders-in-Financial-Futures (TFF) Flat Files -> Databricks Delta (Bronze)
#
# BRONZE LAYER ONLY. Raw rows, all classifications preserved, source-tagged,
# report-date-typed, Friday-release timestamp derived. No feature engineering
# here -- normalization / z-scores / percentiles belong in Silver -> Gold so the
# window + gap policy can be revised without re-ingesting.
#
# Loads (per year, public HTTP -- no S3, no secrets, no entitlement window):
#   com_fin_txt_YYYY.zip  -> bronze_cftc_com   (PRIMARY: futures + options,
#                                               options folded in delta-equivalent)
#   fut_fin_txt_YYYY.zip  -> bronze_cftc_fut   (OPTIONAL: futures only, for the
#                                               incremental-options-effect study)
#
# Design decisions baked in from prior discussion:
# - com_fin and fut_fin have OVERLAPPING column names with DIFFERENT values
#   (options folded in vs not). They go to SEPARATE tables -- never a silent
#   union. Each row is also source-tagged explicitly.
# - The model must key off the FRIDAY PUBLICATION time, not the Tuesday report
#   date, or a backtest leaks ~3 days of hindsight. We derive a release
#   timestamp (nominal Friday 15:30 America/New_York, DST-correct) and expose a
#   safety knob for the holiday-shift edge cases (see RELEASE_SAFETY_DAYS).
# - ALL markets and ALL trader classifications are kept in Bronze. Filtering to
#   your universe (ES, NQ, RTY, VIX, the Treasury curve, SOFR, FX, WTI, Gold,
#   Copper, ...) happens in Silver, not here.
# - Bronze preserves every source column AS STRING. Typing beyond report_date
#   is deferred so a bad cast never drops a raw value.
# - Per-year overwrite via replaceWhere(report_year) makes re-runs safe and lets
#   the current (still-growing) year be refreshed cleanly each week.
#
# No dbutils / secrets required: CFTC history is public.

import io
import zipfile
from datetime import datetime, timezone

import pandas as pd
import requests

from pyspark.sql import SparkSession, functions as F, types as T


# =============================================================================
# CONFIG
# =============================================================================

CATALOG = "bootcamp_students"
SCHEMA = "evangoh_capstone"
CATALOG_SCHEMA = f"{CATALOG}.{SCHEMA}"

# TFF (financial) history begins mid-2010; earlier years 404 and are skipped.
START_YEAR = 2022
END_YEAR = 2026

# com_fin is primary. Set LOAD_FUT_FIN=False to skip the futures-only comparison.
LOAD_COM_FIN = True
LOAD_FUT_FIN = True

# CFTC serves the annual zips from this history path.
BASE_URL = "https://www.cftc.gov/files/dea/history"

# Some CFTC edge nodes reject the default python-requests UA. Use a contactful one.
HTTP_HEADERS = {"User-Agent": "capstone-research (evangoh) contact@example.com"}
HTTP_TIMEOUT = 120

# --- Release-timestamp policy -------------------------------------------------
# COT/TFF is an as-of-TUESDAY snapshot published FRIDAY ~15:30 ET. Nominal
# release = report_date + 3 days. On Monday-holiday weeks the report shifts to
# Wednesday and release slips to the following Monday, so the nominal Friday can
# sit BEFORE the true release -> lookahead risk in those specific weeks.
#
# RELEASE_SAFETY_DAYS lets you push the assumed availability later without a
# calendar:
#   0 -> nominal Friday 15:30 ET (freshest; wrong on a handful of holiday weeks)
#   3 -> assume availability the following Monday (no-lookahead-safe, costs the
#        Fri-afternoon..Mon window)
# For a strict backtest, prefer joining the official CFTC release calendar in
# Silver and overriding release_ts there; this column is the conservative
# default, not ground truth.
RELEASE_SAFETY_DAYS = 0
RELEASE_HOUR_ET = 15
RELEASE_MINUTE_ET = 30
RELEASE_TZ = "America/New_York"

# (dataset tag, url stem, target table, enabled)
DATASETS = [
    ("com_fin", "com_fin_txt", f"{CATALOG_SCHEMA}.bronze_cftc_com", LOAD_COM_FIN),
    ("fut_fin", "fut_fin_txt", f"{CATALOG_SCHEMA}.bronze_cftc_fut", LOAD_FUT_FIN),
]

REPORT_DATE_COL = "Report_Date_as_YYYY-MM-DD"

spark = SparkSession.builder.getOrCreate()
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG_SCHEMA}")

ingest_ts = datetime.now(timezone.utc)


# =============================================================================
# DOWNLOAD (driver-side HTTP; files are small -- tens of thousands of rows/yr)
# =============================================================================

def cftc_url(url_stem: str, year: int) -> str:
    return f"{BASE_URL}/{url_stem}_{year}.zip"


def download_year(url_stem: str, year: int):
    """Fetch one annual TFF zip and return (raw_pandas_df, url).

    Returns (None, url) when the year is not posted (404) so the caller can skip
    gracefully -- e.g. pre-2010 years or a future year not yet published.
    Every column is read as STRING with empties preserved, so Bronze keeps the
    source verbatim and no NaN-float contamination sneaks in.
    """
    url = cftc_url(url_stem, year)
    resp = requests.get(url, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT)

    if resp.status_code == 404:
        return None, url
    resp.raise_for_status()

    # The annual zip holds a single member; let pandas pick it. dtype=str +
    # keep_default_na=False => faithful raw strings, "" stays "".
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        member = zf.namelist()[0]
        with zf.open(member) as fh:
            pdf = pd.read_csv(
                fh,
                dtype=str,
                keep_default_na=False,
                na_values=[],
                low_memory=False,
            )

    return pdf, url


# =============================================================================
# SHAPING (raw preservation + minimal, safe derivations)
# =============================================================================

def sanitize_columns(pdf: pd.DataFrame) -> pd.DataFrame:
    """Delta column names may not contain ' ,;{}()\\n\\t=' -- the TFF long-format
    headers are already underscore-safe, so this is a defensive no-op for these
    files. It only strips whitespace and swaps disallowed chars for '_', keeping
    Bronze faithful while guaranteeing the write can't fail on a header quirk.
    """
    bad = " ,;{}()\n\t="
    renamed = {}
    for c in pdf.columns:
        clean = c.strip()
        for ch in bad:
            clean = clean.replace(ch, "_")
        renamed[c] = clean
    return pdf.rename(columns=renamed)


def to_bronze(pdf: pd.DataFrame, dataset: str, year: int, url: str):
    """Attach report_date / release_ts / lineage to the raw string frame."""
    if REPORT_DATE_COL not in pdf.columns:
        raise RuntimeError(
            f"{dataset} {year}: expected column '{REPORT_DATE_COL}' not found. "
            f"Columns seen: {list(pdf.columns)[:8]}..."
        )

    pdf = sanitize_columns(pdf)

    # All source columns arrive as StringType (raw fidelity).
    sdf = spark.createDataFrame(pdf)

    report_date = F.to_date(F.col(REPORT_DATE_COL), "yyyy-MM-dd")

    # Nominal Friday (report_date + 3) plus the safety buffer, at 15:30 ET,
    # converted to a UTC instant (DST-correct via to_utc_timestamp).
    release_date = F.date_add(report_date, 3 + RELEASE_SAFETY_DAYS)
    release_local = F.concat(
        release_date.cast("string"),
        F.lit(f" {RELEASE_HOUR_ET:02d}:{RELEASE_MINUTE_ET:02d}:00"),
    )
    release_ts = F.to_utc_timestamp(release_local, RELEASE_TZ)

    return (
        sdf
        .withColumn("report_date", report_date)
        .withColumn("report_year", F.year(report_date))
        .withColumn("release_ts", release_ts)
        .withColumn("source_dataset", F.lit(dataset))
        .withColumn("source_file", F.lit(url))
        .withColumn("ingest_ts", F.lit(ingest_ts))
    )


def ensure_delta_table(df, table_name: str):
    if not spark.catalog.tableExists(table_name):
        (
            spark.createDataFrame([], df.schema)
            .write.format("delta")
            .mode("overwrite")
            .saveAsTable(table_name)
        )


def validate_year(df, dataset: str, year: int):
    """Guard against stray rows landing in the wrong year and null report dates."""
    n_null_date = df.filter(F.col("report_date").isNull()).limit(1).count()
    if n_null_date:
        raise RuntimeError(
            f"{dataset} {year}: unparseable {REPORT_DATE_COL} values present."
        )

    n_bad_year = (
        df.filter(F.col("report_year") != F.lit(year)).limit(1).count()
    )
    if n_bad_year:
        # A boundary week whose report_date rolls into an adjacent year is
        # possible; surface it loudly rather than silently mixing years.
        raise RuntimeError(
            f"{dataset} {year}: rows found with report_year != {year}."
        )


def write_year(dataset: str, url_stem: str, table_name: str, year: int) -> int:
    pdf, url = download_year(url_stem, year)
    if pdf is None:
        print(f"  \u26a0 {dataset} {year}: not posted (404); skipping")
        return 0
    if len(pdf) == 0:
        print(f"  \u26a0 {dataset} {year}: empty file; skipping")
        return 0

    df = to_bronze(pdf, dataset=dataset, year=year, url=url)
    validate_year(df, dataset=dataset, year=year)

    ensure_delta_table(df, table_name)

    (
        df.write.format("delta")
        .mode("overwrite")
        .option("replaceWhere", f"report_year = {year}")
        .option("mergeSchema", "true")  # tolerate CFTC adding columns over time
        .saveAsTable(table_name)
    )

    n = df.count()
    print(f"  \u2713 {dataset} {year}: {n:>6,} rows -> {table_name.split('.')[-1]}")
    return n


# =============================================================================
# LOAD
# =============================================================================

years = list(range(START_YEAR, END_YEAR + 1))

for dataset, url_stem, table_name, enabled in DATASETS:
    print("\n" + "=" * 80)
    role = "PRIMARY" if dataset == "com_fin" else "OPTIONAL (futures-only)"
    print(f"CFTC {dataset.upper()}  [{role}]  -> {table_name}")
    print("=" * 80)

    if not enabled:
        print("  (disabled via config; skipping)")
        continue

    total = 0
    loaded_years = 0
    for year in years:
        try:
            n = write_year(dataset, url_stem, table_name, year)
        except Exception as e:
            # One bad year shouldn't lose the rest of the history already written.
            print(f"  \u2717 {dataset} {year}: {e}")
            continue
        if n:
            total += n
            loaded_years += 1

    print(
        f"\nCompleted {dataset}: {total:,} rows across {loaded_years} year(s) "
        f"[{START_YEAR}-{END_YEAR} requested]"
    )


# =============================================================================
# VALIDATION
# =============================================================================

print("\n" + "=" * 80)
print("CFTC BRONZE VALIDATION")
print("=" * 80)

for dataset, _url_stem, table_name, enabled in DATASETS:
    if not enabled or not spark.catalog.tableExists(table_name):
        continue

    print(f"\n{table_name}")
    (
        spark.table(table_name)
        .groupBy("source_dataset", "report_year")
        .agg(
            F.count("*").alias("rows"),
            F.countDistinct("Market_and_Exchange_Names").alias("markets"),
            F.min("report_date").alias("min_report_date"),
            F.max("report_date").alias("max_report_date"),
            F.min("release_ts").alias("min_release_ts"),
            F.max("release_ts").alias("max_release_ts"),
            F.countDistinct("source_file").alias("source_files"),
        )
        .orderBy("report_year")
        .show(truncate=False)
    )


# =============================================================================
# NOTES
# =============================================================================

print("\n" + "=" * 80)
print("CFTC BRONZE LOAD COMPLETE")
print("=" * 80)
print(
    """
Next (Silver):
  - Filter to the capstone universe on Market_and_Exchange_Names.
  - Reindex each market onto a COMPLETE weekly grid (holiday/shutdown gaps),
    decide fill policy (ffill positioning vs leave NaN), set rolling min_periods.
  - Normalize by Open_Interest_All BEFORE any z-score / percentile.
  - For Treasuries / SOFR / VIX: treat Lev-Money net as structure/crowding,
    NOT directional sentiment (basis trade; structural vol-seller short).

Model timestamp: use release_ts (Friday publication), never report_date.
  RELEASE_SAFETY_DAYS is currently {}. For a strict no-lookahead backtest,
  join the official CFTC release calendar in Silver and override release_ts.
""".format(RELEASE_SAFETY_DAYS)
)