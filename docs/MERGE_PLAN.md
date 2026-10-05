# Merge Plan: IBKR_workbench + Rag_workbench → quant_platform

**Date:** 2026-09-02  
**Target:** `/Workspace/Users/evangohsg@gmail.com/Capstone/quant_platform/`  
**Schema:** `bootcamp_students.evangoh_capstone`  
**Deployment:** Databricks App (FastAPI + React)

---

## Current State

| Repo | Purpose | Status |
|---|---|---|
| `IBKR_workbench/` (Git folder) | Market data ETL (Polygon, IBKR, EDGAR, COT, yFinance), DuckDB storage, Streamlit dashboard, text-to-SQL chat | Fully built, DuckDB-based, has DATABRICKS_MIGRATION.md inventory |
| `Rag_workbench/` (Git folder) | Enterprise RAG for SEC filings — FastAPI+React, LangGraph, hybrid retrieval, XBRL verification, guardrails, audit trail | Fully built, deployed to HF Spaces |
| `quant_platform/` (workspace folder) | Merged target — scaffolded via `00_project_setup` notebook | Structure created, files copied, **nothing executed yet** |

The `00_project_setup` notebook already defines the unified directory tree, component mapping, `delta_adapter.py`, ontology YAMLs, and `app.yaml`. This plan builds on that scaffold.

---

## Phase 0 — Foundation (Day 1)
> Goal: Catalog/schema ready, Delta tables created, scaffold verified.

### 0.1 Execute the setup notebook
- Run `00_project_setup` cells 1-12 to:
  - Write `db/delta_adapter.py` (Spark SQL replacement for DuckDB `get_connection()`)
  - Write ontology YAMLs (`business_terms`, `metric_definitions`, `join_hints`, `table_semantics`)
  - Scaffold `app.yaml` + `app.py`
  - Copy KEEP components from both source repos
  - Verify directory structure

### 0.2 Create Delta tables
- Run `01_ingest_market_data` to create the bronze tables:
  - `bronze_ohlcv`, `bronze_options_quotes`, `bronze_options_trades`
  - `bronze_polygon_snapshots`, `bronze_polygon_tickers`
  - `bronze_cot`, `staging_yf_bars`, `staging_yf_indices`
- Run the `sec_rag_ingest` job (or `python pipelines/sec_rag_ingest.py`) to create:
  - `bronze_sec_filings_v2`, `sec_ingest_log`, `sec_cik_mapping_log`

### 0.3 Validate schema
- Confirm all tables exist in `bootcamp_students.evangoh_capstone`
- Verify `delta_adapter.py` write functions match table schemas

---

## Phase 1 — ETL Rewiring (Days 2-3)
> Goal: All extraction clients write to Delta instead of DuckDB.

### 1.1 Rewire IBKR extraction clients
Each file in `etl/` needs `get_connection()` replaced with `delta_adapter` calls:

| File | DuckDB Call → Delta Call | Priority |
|---|---|---|
| `extract_polygon.py` | `INSERT INTO polygon_bars` → `delta_adapter.write_bronze_ohlcv()` | P0 — primary data source |
| `extract_options.py` | DuckDB inserts → `delta_adapter.write_bronze_options_quotes()` | P0 |
| `extract_edgar.py` | DuckDB inserts → `delta_adapter.write_bronze_sec_filings()` | P0 |
| `extract_cot.py` | DuckDB inserts → `delta_adapter.write_bronze_cot()` | P1 |
| `extract_yfinance.py` | DuckDB inserts → `delta_adapter.write_bronze_yf_*()` | P1 |
| `extract_stocks.py` | DuckDB inserts → Delta writes | P2 (requires TWS) |
| `extract_options.py` (IBKR live) | DuckDB inserts → Delta writes | P2 (requires TWS) |

**No rewiring needed:** `polygon_client.py`, `ibkr_client.py`, `slippage.py`, `utils.py` — these are pure API/calculation code.

### 1.2 Migrate existing data
- Use the existing `etl/export_to_databricks.py` script one final time to export DuckDB → Parquet → UC Volume → Delta tables
- Validate row counts match between DuckDB and Delta

### 1.3 Schedule ETL as Lakeflow Jobs
- Create notebook tasks for each data source (one notebook per `--job` from the old `main.py`)
- Schedule: Polygon bars (daily 6AM ET), EDGAR (weekly), COT (weekly Friday), yFinance (daily)

---

## Phase 2 — RAG Services Migration (Days 3-5)
> Goal: Rag_workbench domain logic works against Delta tables + Databricks Vector Search.

### 2.1 Services requiring rewiring
These files in `services/` currently use DuckDB or pgvector and need Delta/Vector Search adapters:

| File | Change Needed |
|---|---|---|
| `edgar_adapter.py` | Replace DuckDB/pgvector queries → Spark SQL against `bronze_sec_filings` / `bronze_edgar_facts` |
| `graph_rag_engine.py` | Replace DuckDB graph triple queries → Delta table for `gold_graph_triples` |
| `langgraph_engine.py` | Rebind tool functions to new `agent/tools_retrieval.py` |
| `chat_engine.py` | Replace DuckDB text-to-SQL → Spark SQL or Genie Space queries |

### 2.2 Services that work as-is (no DB dependency)
- `xbrl_parser.py`, `xbrl_validator.py`, `xbrl_mapper.py` — pure XBRL logic
- `financial_calc.py` — deterministic Python math
- `sec_client.py`, `sec_analyzer.py` — SEC REST API calls
- `sentiment.py` — Loughran-McDonald NLP, pure Python
- `schema_validator.py`, `semantic_validator.py` — validation logic
- `verifier.py` — NLI entailment checking
- `confidence_scorer.py`, `calibration.py` — scoring logic
- `structure_chunker.py`, `peer_comparison.py` — pure computation

### 2.3 Vector Search setup
- Create gold-layer tables for embeddings:
  - `gold_ticker_descriptions` (text from Polygon reference data)
  - `gold_edgar_chunks` (chunked 10-K text from `structure_chunker.py`)
- Create Delta Sync Vector Search indexes on both gold tables
- Replace `rag_engine.py` (DuckDB HNSW) and `hybrid_retriever.py` (BM25+dense) with Vector Search SDK calls
- Replace `reranker.py` cross-encoder with Databricks Foundation Model endpoint or keep as custom model

### 2.4 Guardrails migration
From `Rag_workbench/api/services/guardrails/`:
- Input rails (injection/safety) → port to `agent/guardrails.py`
- Dialog rails (on-topic enforcement) → merge with agent orchestrator
- Output rails (PII masking) → keep as post-processing step

---

## Phase 3 — Agent & Frontend (Days 5-7)
> Goal: Unified AI agent and React frontend working on Databricks App.

### 3.1 Agent layer (`agent/`)
- **`tools_retrieval.py`** — 8 read-only tools:
  - `get_signal` (model scores from gold tables)
  - `search_market` (OHLCV lookup)
  - `search_sec` (EDGAR filing search via Vector Search)
  - `get_cot` (COT positioning)
  - `get_portfolio` (IBKR paper positions)
  - `get_watchlist` (user watchlist from Lakebase)
  - `get_model_perf` (MLflow model metrics)
  - `get_options_chain` (Greeks + IV surface)
- **`tools_write.py`** — 6 write tools:
  - `add_watchlist`, `add_note`, `submit_order_intent`, `approve_order`, `cancel_order`, `record_trade`
- **`guardrails.py`** — deterministic risk checks:
  - Ticker allow-list, notional limit ($50K), buying power check, stale signal rejection
- **`orchestrator.py`** — LangGraph agent that routes between tools

### 3.2 Frontend (`frontend/`)
Copy entire `Rag_workbench/frontend/` and extend:

| Existing (from Rag_workbench) | New Pages (from IBKR_workbench concepts) |
|---|---|
| SEC Explorer page | Market Dashboard (OHLCV + signals + freshness) |
| Agent Workspace (chat + tool traces) | Signal Explorer (model scores + feature contributions) |
| Analytics page | Options Analytics (chain, IV/skew, Greeks) |
| | Order Approval (risk checks + approve/reject) |
| | Portfolio (IBKR paper positions, P&L) |

Key rewiring:
- Update `vite.config.ts` proxy → Databricks App backend
- Add `react-plotly.js` for OHLCV candlestick charts (replacing Streamlit+Plotly)
- Connect all API calls to FastAPI routes in `app.py`

### 3.3 Databricks App deployment
- `app.yaml` — Uvicorn serving `app.py` on port 8000
- `app.py` — FastAPI backend with routes for:
  - `/api/chat/*` (agent endpoints)
  - `/api/market/*` (market data queries)
  - `/api/sec/*` (SEC filing endpoints)
  - `/api/portfolio/*` (positions, orders)
  - `/api/admin/*` (health, config)
- Static React build served by FastAPI or Nginx

---

## Phase 4 — Pipelines & ML (Days 7-10)
> Goal: Medallion transforms and ML model training.

### 4.1 Spark Declarative Pipelines
- **Bronze → Silver** (`pipelines/bronze_to_silver.py`):
  - Clean OHLCV, normalize timestamps, deduplicate
  - Enrich options with normalized Greeks + IV surface
  - Join EDGAR filings + facts
- **Silver → Gold** (`pipelines/silver_to_gold.py`):
  - Technical indicators (SMA, RSI, MACD, Bollinger, ATR)
  - Return features (1d, 5d, 20d, 60d)
  - Volume z-scores, gap signals
  - Point-in-time feature assembly
- **CDF Analytics** (`pipelines/cdf_analytics.py`):
  - Change Data Feed from Lakebase → analytics tables

### 4.2 ML model training
- **Baseline** (`ml/train_baseline.py`): Logistic regression on gold features
- **Challenger** (`ml/train_challenger.py`): XGBoost/LightGBM
- **Walk-forward validation** (`ml/walk_forward.py`): Time-series cross-validation
- **Ablation study** (`ml/ablation.py`): A/B/C/D feature set comparison
- All experiments logged to MLflow

---

## Phase 5 — Evaluation & Audit (Days 10-12)
> Goal: RAG quality evaluation, agent testing, audit trail.

### 5.1 RAG evaluation
- Retrieval evaluation harness: `evals/rag_eval/` (replaces stale `run_eval.py` and `ragas_eval.py`)
  - Deterministic retrieval metrics: recall@k, MRR@10, nDCG@10
  - 8 ablation configurations: 4 modes x 2 ticker filters
  - PIT leakage hard gate, bootstrap CIs, abstention/trap scoring
  - Run: `python -m evals.rag_eval --adapter jsonl --golden ... --corpus ... --embeddings ...`
  - See `evals/rag_eval/README.md` for full documentation
- FinanceBench benchmark: see historical note in `docs/FINANCEBENCH_EVAL_PLAN.md`

### 5.2 Test suite migration
From `IBKR_workbench/tests/` — adapt DuckDB assertions to Delta queries:

| Test Suite | Action |
|---|---|
| `tests/bronze/test_bronze_polygon_bars.py` | Adapt → Delta |
| `tests/bronze/test_bronze_yfinance_*.py` | Adapt → Delta |
| `tests/silver/test_silver_ohlcv_quality.py` | Adapt → Delta |
| `tests/silver/test_silver_conversions.py` | Adapt → Delta |
| `tests/test_slippage.py` | Keep as-is (pure math) |
| `tests/test_extract_*.py` | Keep extraction tests |
| `tests/test_database.py` | Remove (DuckDB-specific) |
| `tests/test_query.py` | Remove (DuckDB query helpers) |
| `tests/gold/test_gold_rag_retrieval.py` | Remove (replaced by Vector Search) |

### 5.3 Audit trail
- Migrate `Rag_workbench/api/db/` audit tables (`audit_runs`, `review_decisions`, `calibration`) to Delta or Lakebase
- Preserve lineage logging from LangGraph engine
- Connect drift detection (`drift_detection.py`) to Delta tables

---

## Phase 6 — Cleanup & Documentation (Day 12+)
> Goal: Remove redundant code, finalize docs.

### 6.1 Remove from quant_platform
Everything marked REMOVE in `DATABRICKS_MIGRATION.md`:
- `db/database.py` (DuckDB bootstrap) — replaced by `delta_adapter.py`
- `rag_engine.py` (DuckDB HNSW) — replaced by Vector Search
- `embed_tickers.py`, `embed_edgar.py` — replaced by Vector Search auto-embed
- `chat_engine.py` (DuckDB text-to-SQL) — replaced by Genie Space
- `dashboard/` (Streamlit) — replaced by React frontend + Databricks App
- `bulk_load_daily.py`, `bulk_load_massive.py` — replaced by Auto Loader
- `export_to_databricks.py` — one-time use, no longer needed
- `query.py`, `rowcount.py` — utility scripts for DuckDB
- `main.py` CLI orchestrator — replaced by Lakeflow Jobs
- Docker files — replaced by Databricks App

### 6.2 Files to keep as reference
- `IBKR_workbench/DATABRICKS_MIGRATION.md` — migration inventory
- `IBKR_workbench/docs/superpowers/` — feature documentation
- `Rag_workbench/docs/` — architecture diagrams
- `Rag_workbench/findings.md` — research findings

### 6.3 Update documentation
- Write unified `README.md` for `quant_platform/`
- Update `docs/architecture.md` with final merged architecture
- Document all API routes and agent tools

---

## Dependency Graph

```
Phase 0 (Foundation)
  │
  ├──► Phase 1 (ETL Rewiring)
  │       │
  │       └──► Phase 4 (Pipelines & ML) ──► Phase 5 (Eval)
  │
  └──► Phase 2 (RAG Services)
          │
          └──► Phase 3 (Agent & Frontend)
                  │
                  └──► Phase 5 (Eval & Audit)
                          │
                          └──► Phase 6 (Cleanup)
```

Phases 1 and 2 can run in parallel after Phase 0.  
Phase 3 depends on Phase 2 (services must work before agent can use them).  
Phase 4 depends on Phase 1 (need bronze data in Delta before transforms).  
Phase 5 depends on Phases 3+4.  
Phase 6 is final cleanup.

---

## Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| Vector Search latency for real-time RAG | High | Benchmark early in Phase 2; fall back to FAISS on compute if needed |
| IBKR TWS not available on Databricks compute | Medium | TWS extraction stays external; use API bridge or run on external machine pushing to Delta |
| Frontend build complexity on Databricks Apps | Medium | Start with API-only App; add static frontend build once backend is stable |
| DuckDB → Delta schema drift during migration | Low | Use `export_to_databricks.py` with schema validation; compare row counts |
| LangGraph agent tool binding complexity | Medium | Test each tool independently before orchestration |

---

## Success Criteria

1. All Polygon/EDGAR/COT/yFinance data lands in Delta tables via scheduled Lakeflow Jobs
2. Auditable RAG pipeline returns cited, XBRL-verified answers from Delta + Vector Search
3. React frontend deployed as Databricks App with all 8 pages functional
4. ML models trained and tracked in MLflow with walk-forward validation
5. Agent can execute end-to-end: query → retrieve → verify → respond with lineage
6. Test suite passes against Delta tables
7. Source workbenches (`IBKR_workbench/`, `Rag_workbench/`) archived — `quant_platform/` is the single source of truth
