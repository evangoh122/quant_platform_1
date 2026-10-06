# WRITE (Codex sol): one-page business case + data inventory + features + quality controls for quant_platform_1

Owner request 2026-10-06: "create a page on the business case and what data we have, what features and checks we have in place". Audience: capstone reviewers / a technical stakeholder who
has not seen the code. Write `docs/BUSINESS_CASE.md` (Markdown, ~2–4 printed pages). Ground EVERY claim in the repo (cite file paths) or in the live facts below; never invent numbers,
users, revenue, performance or edge. Where something is planned rather than built, say "planned" explicitly.

Live facts (Claude, Databricks UC bootcamp_students.evangoh_capstone, 2026-10-06 ~09:30 SGT; SQL warehouse counts):
- 48 tables. Market: bronze_options_day 152,104,694 rows; silver_ohlcv 23,420,557 minute bars; gold_ohlcv_features 23,377,478; silver_options_trades 60,068; gold_options_features 20,318;
  gold_tradable_universe 281,700 rows (557 symbols); market data last ingested ~2026-09-02 (no scheduled incremental ingest yet — planned in docs/data/PLAN-massive-incremental.md on branch
  feat/ui-enhancement).
- SEC: bronze_sec_filings_v2 191,248 rows (225 tickers, 2,845 10-K/10-Q filings since 2024-09); silver_sec_sections 133,886 chunks across 229 tickers; gold_sec_chunk_embeddings 133,886
  (BAAI/bge-small-en-v1.5, complete); gold_sec_coverage 558 tickers, 230 with chunks; silver_sec_entities 90,456.
- XBRL fundamentals (new): bronze_sec_xbrl_facts / silver_sec_xbrl_facts 129,822 facts for 5 pilot tickers (NVDA, AAPL, MSFT, AMD, XOM); 59,610 resolved to SEC acceptance time, 70,212
  quarantined (filing outside the 2024-09+ filing window). Bronze in open PR #42; silver on a stacked branch; gold quarterly fundamentals planned.
- CFTC COT: gold_cot_features 1,464. FRED/Fed: bronze_fed_series, bronze_economic_metrics exist.
- Model: gold_model_features 40,983 snapshots (1/day/symbol); gold_trading_signals 35 baseline signals. Baseline = logistic regression, 1-trading-day horizon (PR #40), hold-out AUC 0.533,
  explicitly labelled "no validated trading edge".
- Lakebase (Postgres) operational store for watchlists, research notes, orders, agent actions; outbox CDC → Delta analytics (analytics_agent_activity, analytics_usage_daily, …).
- App: Databricks App (FastAPI + React) "quant-platform-dev"; AI research agent with governed SEC retrieval (hybrid BM25 + vectors, point-in-time), plain-prose answers, fail-closed
  tool-call validation, one corrective retry (PR #39).
- Merged since submission: #38 (uv CI), #39 (agent), #40 (signals PIT/1-day), #41 (SEC Explorer equity filter), #28 (SEC universe), #43 (share-class tickers). Open: #42 (XBRL bronze), #44
  (serverless job entry points). UI redesign A1–A5 on feat/ui-enhancement (not deployed yet).

Required sections:
1. Business case — the problem (fragmented market + filings research, unverifiable AI answers), who it serves, what the platform does, why this architecture (Databricks medallion + Lakebase +
   governed agent), and what is honestly NOT claimed (no trading edge, baseline signals only, paper broker scaffold).
2. Data inventory — a table per domain (market, options, SEC text, XBRL, COT/macro, model, operational/Lakebase, analytics): source, tables, row counts above, freshness, PIT key.
3. Features — what a user can do today (screens/API/agent) and what is planned (UI A1–A5, Plan B XBRL visuals/knowledge graph, analytics metrics, Massive incremental ingest), with file pointers.
4. Checks and controls — data quality (quarantine tables, PIT rules: SEC acceptance time, purged splits, refit cutoff), security (identity dependency, demo gate, parameterized SQL, secret
   handling, fail-closed agent), engineering process (MiMo builds → checker (DeepSeek, Codex luna fallback) → Codex review → Claude live review → PR + CodeRabbit; mutation testing; CI jobs:
   Python tests, Frontend, bundle validation, secret scan, dependency audit), and known limitations.
5. A short "numbers at a glance" box at the top.
Read the repo (README.md, docs/, api/, agent/, pipelines/, silver/, gold/, ml/, resources/jobs.yml, .github/workflows/ci.yml, .agents/PROTOCOL.md) to cite correctly. Write only
docs/BUSINESS_CASE.md. Print a 5-line summary when done.
