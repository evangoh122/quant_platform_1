# PLAN request (Codex, planner): real Analytics metrics (owner chose "Build real metrics", 2026-10-06)

The deployed Analytics screen shows: Model Performance / Latency (p50/p95) / Stream Freshness "empty … appear once the analytics pipeline
populates it", and Agent Activity rendering "—" in every cell. Facts (Claude, live): analytics_model_performance, analytics_latency and
analytics_stream_freshness DO NOT EXIST and no pipeline in the repo writes them (only api/routes/analytics.py:21-24 and db/delta_adapter.py:489-491
reference them; notebooks/archive/00_project_setup.py:696 sketches model performance). analytics_agent_activity exists with 4 rows but renders "—".
Existing analytics: pipelines/lakebase_analytics.py (Lakebase outbox CDC → analytics_usage_daily, analytics_agent_activity, analytics_order_funnel,
analytics_watchlist_changes, analytics_cdc_state), job lakebase_analytics_refresh (PAUSED). Signals are now a 1-day horizon baseline (PR #40,
ml/baseline_labels.py, scripts/publish_baseline_signals.py); gold_trading_signals holds 35 old 30-minute signals until the owner republishes.
Read origin/main (git show origin/main:<path>) for api/routes/analytics.py, db/delta_adapter.py, pipelines/lakebase_analytics.py,
db/migrations/*.sql (agent_actions has latency? check), agent/runtime.py (AuditEntry: elapsed/latency fields?), frontend Analytics screen.
Write docs/data/PLAN-analytics-metrics.md:
1. Root cause of the Agent Activity "—" (API contract vs frontend field names) with file:line.
2. Each missing table: exact definition from REAL data only — latency p50/p95 per tool/day from agent action timestamps (only if the data
   carries a start/end or elapsed; otherwise say what must be recorded first); stream freshness = per-source max event_ts / max ingest_ts vs now,
   with expected cadence and a stale flag; model performance = realised hit rate / AUC / count per model_version and horizon by joining
   gold_trading_signals to realised next-trading-day returns (PIT: only signals whose label_ts <= now; never score open signals). No synthetic
   or placeholder numbers; empty-with-reason states when inputs are missing.
3. Spark transforms (Delta, idempotent MERGE/overwrite-by-partition), job wiring (part of lakebase_analytics_refresh or a new task; stays PAUSED
   until owner approval), API + frontend states (empty/stale/error honest copy — never "appears once the pipeline populates it" when no pipeline
   exists).
4. Build slices AN1..ANn with files, tests that must fail on the current code, named mutations, acceptance. Do not write application code.
Print a short summary.
