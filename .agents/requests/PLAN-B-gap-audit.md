# PLAN request (Codex, planner): Rag_workbench → quant_platform_1 gap audit (addendum to Plan B)

Owner (2026-10-06): "is anything missing from RAG workbench?" Plan B (docs/ui_enhancement/PLAN-B-workbench-visuals-xbrl.md, yours) inventoried
the main visuals. These Rag_workbench items appear in neither Plan B nor OWNER_PLAN.md:
pages — PortfolioHome, StocksList, AuditLog, ProductAnalytics, Presentation, ConjointStudy, Privacy, Terms;
components — MarkdownMessage, DataTable, ChartErrorBoundary, Disclaimer, LegalLayout, AnalyticsNotice, ConjointGate, ConjointSurvey;
services (api/services) — peer_comparison, financial_calc, chart_tool, confidence_scorer, calibration, verifier, semantic_validator,
schema_validator, polygon_verifier, drift_detection, metric_router, graph_rag_engine, rag_engine, chat_engine, langgraph_engine, shadow_runner,
runtime_snapshot, llm_health, sec_analyzer, edgar_adapter, sec_client, embeddings, reranker, hybrid_retriever, _edgar_identity.
Read /home/jianj/code/Rag_workbench (frontend/src/pages, components; api/services; api routes) and this repo (frontend/src, api/, agent/, pipelines/).
Append a section "## 7. Gap audit (2026-10-06)" to docs/ui_enhancement/PLAN-B-workbench-visuals-xbrl.md with one table row per item:
what it does in Rag_workbench | quant_platform_1 equivalent (file path) or "none" | KEEP / ADAPT / SKIP / ALREADY-COVERED | one-line reason.
OWNER_PLAN.md constraints still bind (no review queue, no DuckDB, no LangGraph, no React Flow, no free-form SQL chatbot, no fabricated
confidence scores, no simulated live counters; the owner lifted only the XBRL/graph restriction). For every ADAPT/KEEP item that is not already
in B1–B9, add a new numbered slice (B10, B11, …) in the same format as section 4 (files, data source, states, tests that must fail on the current
code, named mutations, acceptance) and place it in section 5's ordering. Be concrete; do not write application code. Print a short summary.
