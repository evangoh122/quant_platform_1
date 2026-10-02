# Mid-Frequency Quant Trading Platform

**Unified platform merging IBKR_workbench (market data ETL) and Rag_workbench (enterprise SEC RAG) into a single Databricks-native application.**

Schema: `bootcamp_students.evangoh_capstone`  
Deployment: Databricks App (FastAPI + React + Tailwind CSS)

---

## Architecture

```
Data Sources                     ETL (etl/)                    Delta Tables (UC)
─────────────                    ──────────                    ──────────────────
Polygon.io REST  ──────────────► extract_polygon.py  ────────► bronze_ohlcv
IBKR TWS API     ──────────────► extract_stocks/options.py ──► bronze_options_quotes/trades
SEC EDGAR        ──────────────► extract_edgar.py  ──────────► bronze_sec_filings
CFTC COT         ──────────────► extract_cot.py  ────────────► bronze_cot
yFinance         ──────────────► extract_yfinance.py  ───────► staging_yf_*
Finviz           ──────────────► update_tickers.py  ─────────► config/tickers.yaml

Delta Tables                     Pipelines                     Gold Layer
────────────                     ─────────                     ──────────
bronze_ohlcv ────────────────► bronze_to_silver.py ──────────► gold_ohlcv_features
bronze_options_* ────────────► silver_to_gold.py   ──────────► gold_options_features
bronze_sec_filings ──────────► pit_feature_join.py ──────────► gold_model_features
bronze_cot ──────────────────►                     ──────────► gold_trading_signals

Gold Layer                       Interfaces
──────────                       ──────────
gold_trading_signals ──────────► FastAPI API (/api/*) ───────► React Frontend
gold_*_features ───────────────► AI Agent (LangGraph) ───────► Agent Workspace
bronze_sec_filings ────────────► Vector Search ──────────────► SEC Explorer
etl/slippage.py ───────────────► Cost Calculator ────────────► Options Analytics
```

---

## Directory Structure

| Directory | Source | Purpose |
|---|---|---|
| `etl/` | IBKR_workbench | Data extraction clients (Polygon, IBKR, EDGAR, COT, yFinance) |
| `services/` | Rag_workbench | Domain logic (XBRL validation, financial calc, LangGraph, sentiment, guardrails) |
| `db/` | New | Delta adapter (replaces DuckDB), Lakebase client |
| `agent/` | New | AI agent tools (retrieval, write), risk guardrails, orchestrator |
| `execution/` | New | IBKR paper trading bridge |
| `config/` | IBKR_workbench | Ticker universe (11k+ equities), app settings |
| `ontology/` | New | Business terms, metric definitions, join hints, table semantics, filters |
| `pipelines/` | New | Spark Declarative Pipelines (bronze→silver→gold) |
| `ml/` | New | Model training, walk-forward validation, ablation study |
| `strategies/` | New | Trading cost model, signal strategies |
| `frontend/` | Rag_workbench | React + Vite + Tailwind CSS SPA |
| `tests/` | Both | Medallion tests (IBKR) + RAG/service tests (Rag_workbench) |
| `evals/` | Both | FinanceBench eval plan + RAGAS evaluation |
| `scripts/` | Rag_workbench | Data scripts (embedding, graph triples, seeding) |
| `docs/` | Both | Architecture, READMEs, migration guides, planning |

---

## Key Files

| File | Purpose |
|---|---|
| `app.py` | FastAPI backend (all `/api/*` endpoints) |
| `app.yaml` | Databricks App manifest |
| `db/delta_adapter.py` | Drop-in DuckDB replacement — all ETL writes go through here |
| `config/settings.py` | Unified configuration (UC catalog/schema, API keys, risk limits) |
| `agent/guardrails.py` | Deterministic pre-trade risk checks |
| `services/langgraph_engine.py` | LangGraph DAG for auditable RAG |
| `services/financial_calc.py` | Deterministic financial calculations |
| `00_project_setup` | Setup notebook (schema creation, file scaffolding) |
| `01_ingest_market_data` | Bronze table creation for market data |
| `02_ingest_sec_edgar` | Bronze table creation for SEC filings |

---

## Quick Start

```bash
# 1. Run the setup notebook to create schema + tables
#    Execute 00_project_setup, 01_ingest_market_data, 02_ingest_sec_edgar

# 2. Configure secrets
#    Set POLYGON_API_KEY, EDGAR_EMAIL in Databricks Secrets

# 3. Run ETL
#    Schedule extraction notebooks as Lakeflow Jobs

# 4. Build frontend
cd frontend && npm install && npm run build

# 5. Deploy App
#    Databricks Apps → Create → point to this directory
```