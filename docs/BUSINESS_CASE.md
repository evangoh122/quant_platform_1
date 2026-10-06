# Quant Platform: business case, data, features and controls

> **Numbers at a glance — live Unity Catalog facts, 2026-10-06 ~09:30 SGT**  
> **48 tables** · **152,104,694** daily option rows · **23,420,557** minute bars · **133,886** SEC chunks and embeddings · **557** symbols in the tradable universe · **40,983** model snapshots · **35** published baseline signals. The current one-day logistic-regression baseline achieved **0.533 hold-out AUC**; this is **not a validated trading edge**. Market data was last ingested around 2026-09-02 and scheduled incremental ingestion is planned, not operating.

Counts in this page are live facts from `bootcamp_students.evangoh_capstone` at the timestamp above. Repository pointers identify the implementation or governing design; older snapshots in `README.md` and `docs/proposal/row_counts_2026-10-05.tsv` may therefore differ.

## 1. Business case

### The problem and the users

Equity research is fragmented across price and options feeds, regulatory filings, macro series and a researcher's own notes. Joining those sources manually is slow and creates a less visible risk: a backtest or AI answer can use information that was unavailable at the decision time. Generative answers add another problem when they do not expose their evidence or when retrieved filing text is allowed to behave like instructions.

Quant Platform serves a technical researcher, analyst or small quantitative team that needs one governed research surface rather than a collection of notebooks. It is a Databricks-native application for exploring market and filing data, obtaining evidence-backed SEC research, publishing baseline model outputs, and recording operational actions for audit and later analytics (`README.md`; `docs/proposal/CAPSTONE.md`).

### What the platform does

The platform ingests structured market, options, CFTC and macro data plus unstructured SEC filing text into a Delta medallion lakehouse. Silver transformations clean, deduplicate, quarantine and attach availability semantics; gold tables provide research features, a tradable universe, embeddings and model inputs. A FastAPI and React Databricks App reads the governed tables and exposes market, options, filing, signal, agent, portfolio and health workflows (`pipelines/run_silver_gold.py`; `frontend/src/App.tsx`; `api/main.py`).

The AI research agent uses hybrid BM25 and vector retrieval over SEC passages, filters by SEC acceptance time, treats retrieved text as data, and exposes tool activity as evidence. Its proposed actions must pass deterministic validation before execution; the only write tool is a scoped, idempotent research-note write (`agent/runtime.py`; `agent/tools_retrieval.py`; `agent/tools_write.py`; `docs/proposal/CAPSTONE.md`).

### Why this architecture

The medallion design separates raw lineage from cleaned semantics and consumption-ready features, while Delta and Unity Catalog provide a governed analytical layer. Lakebase (Postgres) handles transactional state—watchlists, notes, orders, executions, positions and agent actions—that does not belong in an analytical fact table. A transactional outbox carries those changes back to Delta for aggregate analytics (`db/migrations/001_operational_schema.sql`; `db/migrations/004_analytics_outbox.sql`; `pipelines/lakebase_analytics.py`). This split gives researchers large-scale analytical reads, operational consistency for writes, and an auditable boundary around the agent.

### What is not claimed

This is a research and platform-engineering case, not evidence of profitability. The 35 signals demonstrate the features → model → published table → UI path. They come from an untuned logistic-regression baseline with a one-trading-day horizon and 0.533 hold-out AUC; no validated trading edge is claimed (live fact; `ml/train.py`; `scripts/publish_baseline_signals.py`). Strategy reports are descriptive research (`strategies/results/`). IBKR execution remains a paper-broker scaffold, not a live trading system (`execution/bridge.py`; `frontend/src/screens/PaperPortfolio.tsx`).

## 2. Data inventory

“Freshness” below reports the measured state, not a promised service level. “PIT key” is the time used, or intended to be used, to decide whether information was knowable at a historical decision point.

### Market and options

| Domain / source | Principal tables | Live size | Freshness | PIT key |
|---|---|---:|---|---|
| Massive/Polygon equities | `bronze_ohlcv`, `silver_ohlcv`, `gold_ohlcv_features`, `gold_tradable_universe` | `silver_ohlcv`: 23,420,557 minute bars; `gold_ohlcv_features`: 23,377,478; universe: 281,700 rows / 557 symbols | Last market ingest ~2026-09-02; no scheduled incremental ingest yet | `event_ts` plus `information_available_ts`; split adjustment uses only corporate actions known by the cutoff (`silver/01_silver_ohlcv.sql`; `silver/08_silver_ohlcv_day_adjusted.sql`) |
| Massive/Polygon options | `bronze_options_day`, `silver_options_trades`, `gold_options_features` | 152,104,694; 60,068; 20,318 respectively | Last market ingest ~2026-09-02 | Market/participant event time plus ingest/availability semantics; contract right is normalized in gold (`silver/04_silver_options_trades.sql`; `gold/02_gold_options_features.sql`) |

### Filings, fundamentals and external context

| Domain / source | Principal tables | Live size | Freshness | PIT key |
|---|---|---:|---|---|
| SEC EDGAR text | `bronze_sec_filings_v2`, `silver_sec_sections`, `gold_sec_chunk_embeddings`, `gold_sec_coverage`, `silver_sec_entities` | 191,248 bronze rows: 225 tickers / 2,845 10-K and 10-Q filings since 2024-09; 133,886 chunks across 229 tickers; 133,886 embeddings; coverage: 558 tickers / 230 with chunks; 90,456 entities | Measured 2026-10-06; embedding run complete using BAAI/bge-small-en-v1.5 | `accepted_ts <= as_of`; missing or invalid availability timestamps fail closed in evaluation/retrieval (`silver/05_silver_sec_sections.sql`; `agent/tools_retrieval.py`; `tests/rag/test_rag_eval_round3.py`) |
| SEC XBRL fundamentals | `bronze_sec_xbrl_facts`, `silver_sec_xbrl_facts`; gold quarterly fundamentals **planned** | 129,822 facts for NVDA, AAPL, MSFT, AMD and XOM; 59,610 acceptance-time-resolved; 70,212 quarantined because their filings fall outside the 2024-09+ window | Bronze is in open PR #42; silver is on a stacked branch, not merged here | Resolved SEC filing `accepted_ts`; unresolved facts remain quarantined rather than assigned an invented historical availability time |
| CFTC COT | `bronze_cftc_fut`, `bronze_cftc_com`, `silver_cot_positions`, `gold_cot_features` | `gold_cot_features`: 1,464 | Measured 2026-10-06; no separate latest-source timestamp reported | Report/as-of date and publication availability (`silver/07_silver_cot_positions.sql`; `gold/04_gold_cot_features.sql`) |
| Federal Reserve / FRED | `bronze_fed_series`, `bronze_economic_metrics` | Tables exist; current row counts not supplied in the live facts | Measured table existence 2026-10-06 | Ingest time for bootstrapped revised series; revised macro is not true vintage data (`docs/BRONZE_REFRESH_PLAN.md`) |

### Model, operational and analytics

| Domain | Principal tables | Live size | Freshness | PIT key |
|---|---|---:|---|---|
| Model and signals | `gold_model_features`, `gold_trading_signals` | 40,983 daily symbol snapshots; 35 signals | Signals published baseline output; measured 2026-10-06 | `prediction_ts`; one-trading-day label; purged time split; final refit admits only labels observed by the earliest scoring snapshot (`ml/baseline_labels.py`; `ml/train.py`; `scripts/publish_baseline_signals.py`) |
| Lakebase operations | `users`, `watchlists`, `research_notes`, `orders`, `executions`, `positions`, `agent_actions`, approvals and `analytics_outbox` | Live operational store; counts not supplied | Transactional/live when the app dependency is healthy | Row creation/update and event timestamps; writes and their outbox record share a transaction (`db/migrations/001_operational_schema.sql`; `db/migrations/004_analytics_outbox.sql`; `db/migrations/005_agent_runtime.sql`) |
| Delta analytics | `lakebase_change_events`, `analytics_agent_activity`, `analytics_watchlist_changes`, `analytics_order_funnel`, `analytics_usage_daily` | Tables are populated; counts not supplied | On-demand CDC job today, not a continuously scheduled feed | Source outbox event ID/time plus a persisted watermark and idempotent MERGE (`pipelines/lakebase_analytics.py`; `db/migrations/CDC.md`) |

## 3. Features

### Available today

- **Application screens:** Market Dashboard, Signal Explorer, Options Analytics, SEC Filing Explorer, AI Research Agent, IBKR Paper Portfolio, Order Approval, and Analytics / System Health are wired into the React application (`frontend/src/App.tsx`). The SEC Explorer filters to covered equities and shows extracted sections and sources (`frontend/src/screens/SecFilingExplorer.tsx`).
- **APIs:** authenticated routes serve market snapshots, signals, SEC coverage, analytics, portfolio, orders, watchlists and agent chat; health endpoints expose dependency and startup diagnostics (`api/routes/`; `api/main.py`).
- **Governed research:** the agent retrieves point-in-time SEC evidence, responds in plain prose, surfaces auditable tool calls and can save a research note. Invalid model output receives one corrective retry and then fails closed (`frontend/src/screens/ResearchAgent.tsx`; `agent/runtime.py`; `tests/agent/test_runtime.py`).
- **Operational audit:** Lakebase persists user research and paper-workflow state; the outbox-to-Delta pipeline produces agent activity, watchlist, order-funnel and daily usage datasets (`db/migrations/`; `pipelines/lakebase_analytics.py`).

### Explicitly planned or not yet deployed

- **UI redesign A1–A5** is on `feat/ui-enhancement` and is not deployed.
- **Plan B XBRL visuals and knowledge-graph presentation** are planned. The repository already contains SEC knowledge-graph build code, but this statement does not claim the planned UI is live (`sec_kg/`; `pipelines/build_sec_knowledge_graph.py`).
- **Gold quarterly XBRL fundamentals** are planned after the bronze PR #42 and stacked silver work.
- **Expanded analytics metrics and scheduled operation** are planned; the current analytics job is on demand (`pipelines/lakebase_analytics.py`; `docs/rubric/PLAN.md`).
- **Massive incremental ingestion** is planned in `docs/data/PLAN-massive-incremental.md` on `feat/ui-enhancement`; it is not present on this branch and no schedule is active. The in-branch refresh design is `docs/BRONZE_REFRESH_PLAN.md`.

## 4. Checks and controls

### Data quality and point-in-time controls

Bad market rows are separated by a quarantine transform instead of silently entering the clean layer (`silver/02_silver_ohlcv_quarantine.sql`). The options path normalizes call/put variants before aggregation (`gold/02_gold_options_features.sql`; `tests/gold/test_options_right_case.py`). XBRL facts that cannot be reconciled to the covered filing window are quarantined (live fact).

PIT is enforced at several boundaries: SEC retrieval uses acceptance time; market features expose availability time; model validation is chronological and purges overlapping label windows; and final refitting uses only rows whose `label_ts` is no later than the earliest scoring cutoff (`agent/tools_retrieval.py`; `gold/pit_guard.py`; `ml/train.py`; `ml/baseline_labels.py`). Mutation-style tests show that removing PIT filtering causes future documents or rows to leak and the test to fail (`tests/rag/test_hybrid_retriever.py`; `tests/gold/test_pit_leakage.py`; `tests/ml/test_baseline_labels.py`).

### Security and agent governance

Production identity is a dependency: API routes obtain the current application user, while a separately gated public-demo mode disables writes and rejects secret-bearing configuration (`api/deps.py`; `api/demo.py`; `tests/api/test_public_demo_security.py`). SQL reads use fixed identifiers, named parameters, bounded limits and timeouts rather than interpolating user input (`db/delta_adapter.py`; `docs/proposal/CAPSTONE.md`). Credentials are injected through environment variables or Databricks secret scopes and are not committed (`docs/DEPLOYMENT.md`; `.env.example`).

Agent actions pass schema, tool allowlist, budget, symbol/evidence, role and write-authorization checks. Retrieved filing content is untrusted data, and malformed or repeatedly invalid model actions execute no tool: one corrective retry is permitted, then execution fails closed (`agent/runtime.py`; `agent/model_client.py`; `tests/agent/test_runtime.py`). Agent activity is recorded for audit (`db/migrations/005_agent_runtime.sql`).

### Engineering gates

The current owner workflow is: **MiMo builds → DeepSeek checks (Codex luna fallback if unavailable) → Codex reviews → Claude performs live review → PR → CodeRabbit review** (`.agents/PROTOCOL.md` provides the repository's file-based verdict format). Safety properties are expected to have mutation evidence that fails on the old or deliberately weakened code.

CI runs the offline Python suite, frontend type-check/build, Databricks bundle validation when credentials are available, Gitleaks secret scanning, `pip-audit`, and production `npm audit` (`.github/workflows/ci.yml`; `docs/SECURITY.md`). Bundle validation is explicitly skipped when workspace credentials are absent, so a green run does not by itself prove live deployment.

### Known limitations

- Market data is stale relative to the 2026-10-06 measurement date; incremental ingestion is not scheduled.
- XBRL covers five pilot tickers and its bronze/silver work is not fully merged; 70,212 facts are quarantined and gold quarterly fundamentals are planned.
- The baseline has no validated trading edge, and the paper broker is not live execution.
- Revised Fed/FRED history is not first-release vintage data and must not be treated as historically known (`docs/BRONZE_REFRESH_PLAN.md`).
- Analytics refresh is on demand; streaming DLT is built but not deployed (`bundles/streaming/README.md`; `README.md`).
- SEC coverage is broad but incomplete: 230 of 558 coverage tickers currently have chunks (live fact).

