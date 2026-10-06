# PLAN-V — "Show all" visuals (owner request 2026-10-06)

Owner approved all nine visuals from the Codex gpt-5.6-sol proposal below. Branch `feat/ui-visuals` (stacked on `feat/ui-enhancement`). Rules for every slice:
native React SVG (no chart library, no React Flow), shared primitives, accessible table fallback for every chart, honest loading/empty/stale/unavailable states,
missing values are gaps (never zero), and no fabricated series. Each slice: MiMo builds → luna checks → Codex sol reviews → Claude reviews.

| Slice | Visuals | Backend |
|---|---|---|
| V1 | shared chart primitives; options put/call timeline; signal conviction ranking; SEC coverage chart | existing APIs only |
| V2 | filing activity timeline; filing tone / risk-change history; market breadth / regime panel | NEW read-only API routes |
| V3 | agent usage and reliability chart | analytics typed-contract repair (PLAN-analytics-metrics AN1) |
| V4 | bounded knowledge-graph explorer | NEW `/api/research/graph/neighbourhood` (PLAN-B B5) |
| (A5) | price + volume chart | already built on feat/ui-enhancement |

## Codex gpt-5.6-sol proposal (verbatim)

The strongest capstone visuals are those proving the research workflow: market context → evidence → signal → portfolio decision. Prioritize real, point-in-time data over decorative dashboards.

## Buildable now from existing data

1. **Price and volume history — Market Dashboard**  
   **Chart:** adjusted-close line with volume bars.  
   **Source:** existing `GET /api/market/{symbol}`; `silver_ohlcv_day_adjusted(event_date, close, volume, price_basis)`.  
   **Question:** What has the asset done, and was the move supported by volume?  
   **Effort:** S. **Data:** Yes; already implemented on `feat/ui-enhancement`, but market data is stale around 2026-09-02.

2. **Options positioning timeline — Options Analytics**  
   **Chart:** put/call volume stacked bars plus put/call-ratio and volume-anomaly lines.  
   **Source:** existing `/api/market/{symbol}`; `gold_options_features(feature_ts, put_volume, call_volume, put_call_ratio, volume_anomaly_zscore)`.  
   **Question:** Is derivatives activity becoming unusually defensive or speculative?  
   **Effort:** S. **Data:** Yes, across roughly 503 dates. Do not chart historical IV/skew as a continuous series: `iv_atm`, `iv_skew`, term slope and exposure are populated only for the single 2026-09-02 quote snapshot and otherwise null.

3. **Signal conviction ranking — Signal Explorer**  
   **Chart:** sorted horizontal bars or lollipop plot, colored by UP/DOWN.  
   **Source:** existing `GET /api/signals`; `gold_trading_signals(symbol, direction, probability, prediction_ts, model_version, horizon, status)`.  
   **Question:** Which current research candidates have the strongest baseline-model scores?  
   **Effort:** S. **Data:** Yes, 35 published signals. Label these “baseline probabilities,” not expected returns or validated alpha.

4. **SEC research coverage — Platform Overview / SEC Explorer**  
   **Chart:** ranked bars for chunks and filings per ticker, optionally a filings-versus-chunks scatterplot.  
   **Source:** existing `GET /api/sec/coverage`; `gold_sec_coverage(ticker, n_filings, n_chunks, first_filed, last_filed)`.  
   **Question:** How broad and deep is the evidence corpus, and where are its gaps?  
   **Effort:** S. **Data:** Yes: 133,886 chunks across 229 tickers; approximately 230 of 558 coverage tickers have chunks.

5. **Filing activity timeline — SEC Filing Explorer**  
   **Chart:** filings by acceptance date, grouped by form type, with section/chunk density.  
   **Source:** **NEW API** over `silver_sec_sections(ticker, accession_number, form_type, accepted_ts, filing_section, chunk_index)`.  
   **Question:** When did material company information enter the investable information set?  
   **Effort:** M. **Data:** Yes. Use `accepted_ts`, never filing date, for timing.

6. **Filing tone and risk-change history — SEC Filing Explorer**  
   **Chart:** positive/negative/uncertainty rate lines plus risk-change markers.  
   **Source:** **NEW filing-insights API** over `gold_sec_features(information_available_ts, tone_positive, tone_negative, tone_uncertainty, risk_factor_change, filing_similarity, accession_number, form_type)`.  
   **Question:** Is disclosure tone or risk language changing relative to the prior filing?  
   **Effort:** M. **Data:** Yes. Null first-filing comparisons must remain gaps; these are deterministic lexicon measures, not model confidence.

7. **Evidence-backed entity constellation — Knowledge Graph Explorer**  
   **Chart:** bounded node-link neighbourhood with a keyboard-accessible node/edge table.  
   **Source:** **NEW `/api/research/graph/neighbourhood`** from `silver_sec_entities(entity_type, entity_key, entity_value, accession_number, accepted_ts, source_chunk_id)` joined to `silver_sec_sections`.  
   **Question:** Which companies, facts, risks and events co-occur in a filing, and what source passage supports them?  
   **Effort:** L. **Data:** Yes, about 90,456 entities. Edges must say “co-occurs in filing,” not imply causality; enforce server-side node/edge caps.

8. **Market breadth/regime panel — Market Dashboard**  
   **Chart:** RSP/SPY ratio with SMA50, regime bands, and QQQ-minus-SPY 20-day spread.  
   **Source:** **NEW API** over `gold_regime_features(trade_date, rsp_spy_ratio, rsp_spy_ratio_sma50, breadth_regime, qqq_spy_20d, rsp_spy_20d)`.  
   **Question:** Is participation broadening or narrowing beneath headline index performance?  
   **Effort:** M. **Data:** Yes. Describe it as a breadth proxy, not a factor decomposition.

9. **Agent usage and reliability — System Health**  
   **Chart:** daily call bars by tool/status and p50/p95 latency lines.  
   **Source:** existing `/api/analytics` after its typed-contract repair; `analytics_agent_activity(event_date, tool_name, action_type, status, call_count, distinct_users)` and, once populated, `analytics_latency`.  
   **Question:** Does the capstone demonstrate a used, observable application rather than only a data lake?  
   **Effort:** M. **Data:** Agent activity exists; latency does not yet. Do not render absent latency as zero.

## Needs a pipeline first

10. **Quarterly fundamentals with price overlay — Market Dashboard**  
    **Chart:** revenue/margin/FCF series with separately scaled adjusted close.  
    **Source:** planned `/api/research/fundamentals` from `gold_fundamentals_quarterly`; price from `/api/market/{symbol}`.  
    **Question:** Did market revaluation track changes in company fundamentals?  
    **Effort:** L. **Data:** Not ready. Silver XBRL has 129,822 pilot facts for five tickers, but canonical PIT-safe gold quarterly metrics do not exist. Charting raw facts now would mix concepts, units and restatements.

11. **Peer fundamental comparison — Peer Comparison**  
    **Chart:** comparable-value bars for 2–5 explicitly selected companies.  
    **Source:** planned `/api/research/peers`, also dependent on `gold_fundamentals_quarterly`.  
    **Question:** How does a company’s margin, growth or cash generation compare with chosen peers as of the same date?  
    **Effort:** L. **Data:** Not ready. Never rank missing values as zero or silently invent competitors.

12. **Realized model performance — System Health / Model Evidence**  
    **Chart:** hit rate and AUC through evaluation date, with realized-sample counts.  
    **Source:** planned `analytics_model_performance(evaluation_date, model_version, horizon, realised_count, hit_rate, auc, max_label_ts)`.  
    **Question:** Has the baseline performed out of sample after labels actually closed?  
    **Effort:** L. **Data:** Pipeline absent. The documented 0.533 hold-out AUC is a training evaluation, not a live performance series.

**Charting recommendation:** keep the current dependency-free React SVG/CSS approach with accessible table fallbacks. `frontend/package.json` contains no chart library, and Plan B explicitly favors bounded native SVG over adding Recharts or React Flow. Extract shared scales, axes, tooltips and empty-state primitives before reconsidering a library.


## V5 — Positioning (added 2026-10-06, owner: "I don't see any sign of positioning")
CFTC COT (`silver_cot_positions`, `gold_cot_features`) feeds the model (`gold/05_gold_model_features.sql:95-126`) but no API or screen read it, and none of the plans or reviews
flagged that. V5 adds `/api/positioning/cot` and a Positioning screen; options OI/delta exposure is shown as a dated snapshot only. Built right after V1.

## Standing check: model inputs must be visible
Every table that feeds `gold_model_features` must be visible somewhere in the app (chart, table or evidence panel). Reviewers check this on every slice.
