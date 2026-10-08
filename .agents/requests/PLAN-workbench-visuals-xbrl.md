# PLAN request (Codex, planner): bring Rag_workbench visuals + XBRL fundamentals + more coach marks into quant_platform_1

Owner request 2026-10-05: "look at Rag Workbench and see some of the visuals as well XBRL data and coach marks etc ... plan and build those
features in". This OVERRIDES the "No XBRL/Polygon/graph sections yet" line of docs/ui_enhancement/OWNER_PLAN.md Phase 4; every other
OWNER_PLAN constraint still binds (React 18 + Vite + Tailwind; no DuckDB, no free-form SQL chatbot, no LangGraph, no React Flow, no review
queue, no wholesale copy of the 72 KB App.tsx, no fabricated confidence scores, no simulated live counters, baseline signals labelled as such).

Read: /home/jianj/code/Rag_workbench/frontend/src/components/* (FinancialChart, ChartView, KnowledgeGraph, GraphExplorer, GraphAnalytics,
PipelineFlow, ToneAnalysis, AuditTrail, DriftAlert, CoachMarks, tourSteps) and pages/* (RagOverview, MetricsDashboard, SystemDashboard,
Methodology); Rag_workbench api/services/xbrl_parser.py, xbrl_client.py, edgar_adapter.py, peer_comparison.py, chart_tool.py (backend
ideas only — do not port services wholesale). This repo: docs/ui_enhancement/{OWNER_PLAN,PLAN}.md, frontend/src (A1 shell + A2 tours on this
branch), api/ (FastAPI routes; SQL-warehouse adapter db/delta_adapter.py; parameterized queries only), pipelines/, silver/, gold/,
api/services/xbrl_client.py. Workspace tables that exist (bootcamp_students.evangoh_capstone): bronze_sec_filings_v2, silver_sec_sections,
silver_sec_entities, gold_sec_features, gold_sec_chunk_embeddings, gold_ohlcv_features, silver_ohlcv, bronze_options_day, gold_model_features,
gold_trading_signals, analytics tables. NO XBRL table exists yet. Spark-on-Databricks is the processing standard for new data
(bronze → silver → gold, append-only bronze with ingest timestamps, point-in-time `information_available_ts` = SEC acceptance time).

Write docs/ui_enhancement/PLAN-B-workbench-visuals-xbrl.md containing:
1. Inventory: each Rag_workbench visual — what it shows, what data it needs, whether this platform has that data — and a KEEP / ADAPT / SKIP
   decision with a one-line reason.
2. XBRL data lane: SEC companyfacts API → Spark bronze (`bronze_sec_xbrl_facts`) → silver (deduped facts per concept/unit/period, restatement
   handling: keep every filed value with its accession + filed date; PIT view picks the latest value filed on/before as-of) → gold
   (`gold_fundamentals_quarterly`: revenue, gross margin, operating income, net income, EPS diluted, FCF, R&D, segment/geography where available)
   for the SEC-covered tickers; job resource in resources/jobs.yml; rate limit + User-Agent rules; tests that must fail on the old code.
3. API contracts (FastAPI, typed pydantic, parameterized warehouse SQL): fundamentals time series, peer comparison, knowledge-graph
   neighbourhood from silver_sec_entities (bounded node/edge counts), pipeline/lineage status. State empty/stale/unavailable behaviour.
4. Frontend slices, each small enough for one build + check + review round, numbered B1..Bn: e.g. FinancialChart (fundamentals + price
   overlay), Peer comparison, Knowledge-graph view (lightweight SVG/canvas, no React Flow), Pipeline-flow diagram for the Architecture page,
   Filing tone/risk-change panel from gold_sec_features, extra coach-mark tours for the new screens. For each: files, data source, states,
   tests that must fail on the current code, named mutations for the checker, and acceptance commands.
5. Ordering and dependencies with the in-flight work (UI slices A1 r3, A3–A5 still pending; RAG PR #28 universe ingest; agent PR #39), and
   what the agent could gain (e.g. a read-only `get_fundamentals` tool through the existing validator/allowlist — optional, separate slice).
6. Risks: XBRL concept inconsistency (tag aliases per company), units/scales, fiscal calendars, amended filings, chart bundle size.
Keep it concrete and buildable. Do not write application code. Print a short summary to stdout when done.
