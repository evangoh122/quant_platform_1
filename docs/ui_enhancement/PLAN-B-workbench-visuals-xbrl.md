# Plan B: workbench visuals, XBRL fundamentals, and extended tours

This is a planning artifact. It does not implement application code. It extends
the binding constraints in `OWNER_PLAN.md`; the owner's 2026-10-05 request
specifically overrides only the earlier “No XBRL/Polygon/graph sections yet”
line. React 18, Vite, Tailwind, typed FastAPI contracts, parameterized warehouse
queries, Spark/Delta processing, honest state handling, and all other owner-plan
constraints remain in force.

The useful Rag_workbench ideas are interaction and information-design
references, not code to copy. In particular, do not port its 72 KB `App.tsx`,
DuckDB services, LangGraph orchestration, free-form SQL, review queue, React
Flow, Polygon panels, arbitrary confidence scores, or polling that presents
simulated activity as live.

## 1. Rag_workbench visual inventory

| Reference | What it shows | Required data | Data available here now? | Decision | Reason |
| --- | --- | --- | --- | --- | --- |
| `FinancialChart.tsx` | Grouped bars of XBRL facts by concept and period | Normalized concept, label, numeric value, unit, period | Partial: XBRL-like entities exist in `silver_sec_entities`, but there is no dedicated, PIT-safe fundamentals table or API | **ADAPT** | Build from the new gold fundamentals contract and add the requested price overlay; do not chart ad hoc facts from agent output. |
| `ChartView.tsx` | Annual/quarterly line or bar charts and multi-company series | Deterministic annual/quarterly metric series and units | Price history exists; normalized fundamental histories do not | **ADAPT** | Keep annual/quarterly and peer-series ideas, but use a small native SVG/CSS implementation and typed API data rather than adding Recharts immediately. |
| `KnowledgeGraph.tsx` | Typed nodes/edges, truncation, selection, neighbour expansion | Filing-derived entities, relationships, provenance, hard result limits | Partial: `silver_sec_entities` and SEC sections exist; gold KG tables/build also exist, but the requested API source is silver entities | **ADAPT** | Use a bounded server-built neighbourhood and lightweight SVG/canvas; React Flow is prohibited and client-side full-graph loading is unsafe. |
| `GraphExplorer.tsx` | Ticker filtering, node/edge counts, graph empty/error states, evidence drawer | Covered tickers, graph neighbourhood, linked filing excerpt and EDGAR URL | Partial: ticker/entity/accession/source chunk fields exist; evidence can join `silver_sec_sections` | **ADAPT** | Keep filter, counts, and click-to-evidence patterns with one ticker/root at a time; never fetch all triples then filter in the browser. |
| `GraphAnalytics.tsx` | Counts by relationship/entity/company | Stable graph aggregation tables or bounded aggregate queries | Partial, but no product need in the first graph slice | **SKIP (initially)** | It adds query and UI scope before the neighbourhood proves useful; reconsider as a later aggregate-only slice. |
| `PipelineFlow.tsx` | Six processing nodes with success/error/pending styling | Declared lineage plus observed table/job freshness | Partial: lineage and tables are known; no current API proves per-node live execution | **ADAPT** | Render a static HTML/CSS lineage diagram plus observed freshness/status. Do not animate or claim a job is running without evidence. |
| `ToneAnalysis.tsx` | Positive/negative/uncertainty rates and change from prior filing | `gold_sec_features` per filing and prior-filing comparison | Yes: sentiment rates, `risk_factor_change`, `filing_similarity`, accession and PIT timestamp exist | **ADAPT** | Show deterministic lexicon outputs and risk-change values with methodology labels; omit generated summaries/key drivers unless a grounded contract is added later. |
| `AuditTrail.tsx` | Sources, XBRL facts, verification, calculations, and market data | Accession-level provenance, selected facts, math steps, source links | Partial: A4 will add SEC evidence; XBRL provenance arrives with this lane | **ADAPT** | Extend A4 evidence cards later with filed fact/accession/unit/PIT provenance; skip the Polygon section and do not revive generic raw JSON by default. |
| `DriftAlert.tsx` | Agreement/concept-spike health card with polling | Measured drift metrics, thresholds, last observation time | No equivalent measured XBRL drift contract exists | **SKIP** | Its fallback defaults can look measured. Add drift only after materialized quality metrics and explicit timestamps exist. |
| `CoachMarks.tsx` | Spotlight tour with keyboard navigation and missing-target fallback | Stable `data-tour` targets and versioned local-storage keys | Yes: A2 provides the accessible host and existing application/agent/architecture tours | **KEEP / EXTEND** | Reuse the current qp1 tour implementation, not the older disclaimer-dependent component; add screen-specific keys and targets after each screen exists. |
| `tourSteps.ts` | Landing, chat, and overview tour copy | Screen-specific targets and navigation handoff | Partial: A2 targets exist; new B screens do not | **ADAPT** | Add concise fundamentals, graph, and filing-insights tours with qp1 copy and versioned keys; no cross-screen step should target an unmounted element. |
| `RagOverview.tsx` | Product story, launch/methodology actions, business case | Static verified claims and navigation | A3 is already specified to supply this role | **SKIP as a separate port** | A3 `PlatformOverview` is the native destination; only reuse its narrative hierarchy where consistent with verified snapshot labels. |
| `MetricsDashboard.tsx` | Retrieval/evaluation metrics and drift polling | Materialized evaluation/drift metrics | Partial analytics contract, but not these specific measurements | **SKIP** | The planned Activity Analytics screen owns measured platform metrics; do not create zeros or health claims from absent data. |
| `SystemDashboard.tsx` | Corpus counts, pipeline diagram, status and refresh | Typed health and measured table statistics | Partial: health exists; A1/A3 and later Activity Analytics cover it | **ADAPT narrowly** | Put measured lineage/table freshness into the Architecture page and preserve `SystemHealth`; avoid a second overlapping dashboard. |
| `Methodology.tsx` | Long-form ingestion, retrieval, verification and evaluation explanation | Stable design documentation | Yes as documentation, not a new standalone product route | **ADAPT narrowly** | Add XBRL methodology/provenance copy to Architecture & Tests rather than introducing another navigation destination. |

`ReviewQueue.tsx` and the old review APIs remain explicitly out of scope.

## 2. XBRL data lane

### 2.1 Source, identity, and ingestion

Use the SEC Company Facts endpoint
`https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` for each
SEC-covered ticker/CIK from the canonical universe configuration. Do not use a
hard-coded frontend or service ticker map. Company Facts is the source of
standardized facts; existing filing metadata in `bronze_sec_filings_v2` is the
source of the SEC **acceptance timestamp** for an accession.

SEC access rules are build requirements:

- Require `EDGAR_USER_AGENT` in the form `application/company contact-email`;
  fail configuration validation rather than ship a placeholder identity.
- Send that User-Agent on every request, cap the process at **no more than 10
  requests/second** (target 8 requests/second with jitter), use bounded
  exponential backoff for `429`, `403`, and transient `5xx`, honor
  `Retry-After`, and cap retries.
- Use connect/read timeouts, bounded concurrency, and an ingest manifest with
  CIK, HTTP status, attempt count, payload hash, bytes, start/end timestamps,
  and error category. Never log response bodies, credentials, or contact data.
- Cache within one run by CIK and skip a write when the same payload hash was
  already committed for that CIK/run; a later changed payload is a new bronze
  observation.

Add a Spark entry point such as `pipelines/ingest_sec_companyfacts.py`; the
HTTP fetch may execute on the driver with bounded concurrency, but parsing and
normalization must be Spark transformations. Add a task to
`resources/jobs.yml` before the silver/gold SEC task, passing catalog/schema
and the canonical universe resource. The job must be rerunnable and must not
depend on a local DuckDB database or a request-time HTTP fetch.

### 2.2 Bronze: append-only raw observations

Create `bootcamp_students.evangoh_capstone.bronze_sec_xbrl_facts` as an
append-only Delta table. One row represents one raw Company Facts unit entry
observed in one payload. Minimum columns:

```text
ingest_run_id, ingested_at, source_url, payload_hash,
cik, entity_name, ticker, taxonomy, concept, label, description,
unit, value_raw, value_decimal,
period_start, period_end, instant, fiscal_year, fiscal_period,
form_type, accession_number, filed_date, frame,
raw_fact_json, source_updated_at
```

Preserve raw strings/JSON even when typed parsing fails. Bronze uniqueness is
not enforced across runs: repeated source observations remain auditable.
`ingested_at` records collection time only; it is never the market-availability
time of a filing fact.

### 2.3 Silver: exact-ingest dedupe while retaining restatements

Create `silver_sec_xbrl_facts`. Normalize CIK/ticker, taxonomy/concept, dates,
numeric values and units. Resolve `information_available_ts` by joining
`accession_number` to `bronze_sec_filings_v2.accepted_ts`. Company Facts'
`filed` date is retained as `filed_date`, but must not replace acceptance time.
Facts whose accession cannot be resolved receive an explicit quality status
and are excluded from PIT/gold publication until backfilled; do not guess an
acceptance timestamp.

Deduplicate repeated **ingestions of the same filed fact**, while retaining
every value filed by the issuer. The retained natural identity is at least:

```text
cik, taxonomy, concept, unit, period_start, period_end/instant,
fiscal_year, fiscal_period, form_type, accession_number, frame
```

For exact duplicates of that identity, keep the latest successfully parsed
bronze observation and preserve first/last observed timestamps. Different
accessions are different facts even when concept/unit/period/value match.
Amendments and later filings that restate comparative periods therefore remain
separate rows.

Expose a PIT view (for example `silver_sec_xbrl_facts_asof`) whose consumers
provide `:as_of`. It filters `information_available_ts <= :as_of` and selects
the latest filed value for each
`cik + taxonomy + concept + unit + period/context`, ordered by
`information_available_ts DESC, filed_date DESC, accession_number DESC`.
This is the only selection rule allowed for historical backtests or as-of API
requests. Current-view endpoints use an explicit server timestamp and the same
rule.

### 2.4 Gold: quarterly canonical fundamentals

Create `gold_fundamentals_quarterly`, one row per
`ticker + fiscal_year + fiscal_quarter + information_available_ts` publication
version. The table keeps publication versions so an as-of query can reproduce
what was known. Include:

```text
ticker, cik, fiscal_year, fiscal_quarter, period_start, period_end,
information_available_ts, filed_date, accession_number, form_type,
revenue, gross_profit, gross_margin, operating_income, net_income,
eps_diluted, operating_cash_flow, capital_expenditure, free_cash_flow,
research_and_development,
currency_unit, eps_unit,
revenue_concept, gross_profit_concept, operating_income_concept,
net_income_concept, eps_diluted_concept, operating_cash_flow_concept,
capital_expenditure_concept, research_and_development_concept,
segment_json, geography_json, quality_flags, processed_ts
```

Use a reviewed alias registry, not first-match heuristics embedded in API code.
Aliases are ordered per canonical metric and may have a company override with
an effective date. Record the selected source concept in every gold row.
Compute `gross_margin = gross_profit / revenue` only when both facts share a
compatible period/context and currency. Compute
`free_cash_flow = operating_cash_flow - capital_expenditure`, normalizing the
cash-outflow sign once according to the selected capex concept; keep both
inputs and a quality flag. Do not silently coerce units or multiply by guessed
scales.

Company Facts does not reliably expose every issuer's dimensional segment and
geography contexts. Populate `segment_json`/`geography_json` only when source
dimensions are explicitly available and provenance can be retained; otherwise
return `null`/empty with `segment_unavailable` or `geography_unavailable` in
`quality_flags`. Never infer a segment allocation from narrative text.

Fiscal quarter labels come from SEC fiscal metadata/context duration, not
calendar month alone. For cumulative year-to-date facts, derive a discrete
quarter only when compatible prior cumulative facts exist under the same
concept/unit/fiscal calendar; flag rather than fabricate missing quarters.

### 2.5 XBRL tests that fail on the old code

Add focused tests under `tests/bronze/test_sec_companyfacts.py`,
`tests/silver/test_sec_xbrl_facts.py`, and
`tests/gold/test_fundamentals_quarterly.py`:

1. The SEC client rejects a missing/placeholder User-Agent, sends the configured
   identity, respects `Retry-After`, and cannot exceed the request-rate cap.
2. Bronze appends two changed payload observations and preserves raw malformed
   facts instead of losing them.
3. Reingesting an identical payload does not create duplicate silver filed
   facts, while two accessions for the same concept/unit/period both survive.
4. `information_available_ts` equals the accession's SEC `accepted_ts`; a fact
   without a resolvable accession is not published to gold.
5. An as-of query before an amendment returns the original value and an as-of
   query after acceptance returns the amended/restated value.
6. Alias selection records the chosen concept and a company override cannot
   leak outside its effective dates/company.
7. USD and shares/EPS units do not mix; incompatible units set a quality flag
   and suppress the derived metric.
8. Non-calendar fiscal quarters and cumulative YTD facts produce correct
   discrete quarters or an explicit unavailable flag.
9. FCF and gross margin use compatible inputs and never divide by zero.
10. The job resource orders Company Facts ingestion before silver/gold and is
    idempotent on a second run.

Named checker mutations: replace acceptance time with `filed_date`; drop
`accession_number` from the silver key; sort restatements oldest-first; accept
a placeholder User-Agent; remove the rate limiter; treat calendar quarter as
fiscal quarter; combine mismatched units; flip the capex sign twice; publish an
unresolved accession; and overwrite bronze instead of appending. The tests
must catch each mutation.

Backend acceptance for this slice:

```sh
pytest -q tests/bronze/test_sec_companyfacts.py tests/silver/test_sec_xbrl_facts.py tests/gold/test_fundamentals_quarterly.py
pytest -q tests/gold/test_pit_leakage.py tests/test_schema_env_override.py
```

## 3. API contracts

Implement additive routes in a new `api/routes/research.py` (or equivalently
small purpose-named route modules), register them in `api/main.py`, define
Pydantic v2 models in `api/schemas.py`, mirror them in
`frontend/src/api/types.ts`, and add client calls in
`frontend/src/api/client.ts`. Every warehouse query must select named columns,
use native `:name` parameters through `db/delta_adapter.py`, validate enum-like
metric/period inputs against an allowlist, and enforce a server-side bound.
Never interpolate ticker, root ID, dates, metrics, table names supplied by the
caller, or limits into SQL.

Use the existing `Freshness` and `Envelope[T]` semantics. `404` is reserved for
an invalid/unknown resource; a valid covered symbol with no rows is HTTP 200
with `empty=true`. Dependency failure is HTTP 200 with an unavailable envelope
when a partial screen can still render, or `503` with a typed safe detail when
the whole response cannot be formed. Never expose warehouse exception text.

### 3.1 Fundamentals time series

`GET /api/research/fundamentals/{symbol}?metrics=revenue,gross_margin&frequency=quarterly&as_of=<ISO-8601>&limit=20`

- `symbol`: normalized against the SEC-covered universe.
- `metrics`: allowlisted canonical metrics; maximum six.
- `frequency`: `quarterly | annual`; annual is a deterministic aggregation or
  FY row, never four-quarter arithmetic over incompatible versions.
- `as_of`: optional, defaults to the server request time and is echoed back.
- `limit`: 1–40, default 20.

Response:

```text
FundamentalsResponse {
  symbol, cik, frequency, as_of,
  series: Envelope<FundamentalPoint>, available_metrics, warnings
}
FundamentalPoint {
  metric, label, value, unit, fiscal_year, fiscal_quarter,
  period_start, period_end, information_available_ts,
  filed_date, accession_number, form_type, source_concept,
  quality_flags
}
```

The PIT filter is mandatory even when `as_of` is omitted. Empty means the
symbol is covered but no qualifying facts exist. Stale means data exists but
the latest accepted fact is older than a documented metric-independent
threshold displayed in `freshness.detail`; stale data remains visible.

### 3.2 Peer comparison

`GET /api/research/peers?symbols=NVDA,AMD,INTC&metric=gross_margin&period=latest&as_of=<ISO-8601>`

- Require 2–5 unique covered symbols. The client supplies the peer set in the
  first slice; do not silently invent “competitors.” A later curated peer-group
  registry can prefill it and must disclose its source.
- Allow one canonical metric and `latest | FYyyyy | FYyyyyQn`.
- Apply the same `as_of` to every symbol, returning the selected period and
  provenance per row. Do not compare mismatched currency units.

Response is `PeerComparisonResponse { metric, label, unit, period, as_of,
peers: Envelope<PeerPoint>, warnings }`; `PeerPoint` contains symbol, value,
rank (nullable when values are not comparable), fiscal period, acceptance
timestamp, accession, source concept, and quality flags. Missing peers remain
listed with `value=null` and an explanation; they are not converted to zero.

### 3.3 Knowledge-graph neighbourhood

`GET /api/research/graph/neighbourhood?symbol=NVDA&root_id=<id>&depth=1&max_nodes=30&max_edges=60`

- Source the first implementation from `silver_sec_entities` plus
  `silver_sec_sections` provenance, as requested. Define deterministic node IDs
  from typed normalized values and deterministic edge IDs from endpoints,
  accession and relation.
- Allow depth only `1 | 2`, cap nodes at 50 and edges at 100 regardless of
  caller input, and return `truncated=true` with the effective limits.
- If `root_id` is absent, root at the company node. Expansion repeats the same
  bounded server call; never return the entire entity table.
- Return only evidence-backed relations such as company-has-metric,
  company-has-risk, company-filed-event and metric-from-filing. Do not label
  co-occurrence as causation or competition.

Response: `GraphNeighbourhoodResponse { symbol, root_id, nodes, edges,
truncated, limits, freshness }`. A `GraphNode` has ID, type, label and safe
summary fields; a `GraphEdge` has ID, source, target, relation,
accession_number, accepted_ts, source_chunk_id and optional source URL. Unknown
root is `404`; no graph for a valid symbol is a typed empty response.

### 3.4 Pipeline and lineage status

`GET /api/research/lineage`

Return declared edges plus observed table state:

```text
LineageResponse {
  generated_at,
  nodes: LineageNode[], edges: LineageEdge[],
  freshness
}
LineageNode {
  id, label, layer, table_name,
  state: fresh|stale|empty|unavailable,
  row_count: int|null,
  latest_information_available_ts: str|null,
  latest_processed_ts: str|null,
  detail
}
LineageEdge { source, target, label }
```

Only expose row count/timestamps actually queried from allowlisted tables.
`pending` or `running` is not part of this contract because table metadata does
not prove a live job state. A table missing or denied is `unavailable` with a
safe detail; an existing zero-row table is `empty`, never a healthy zero.

API tests in `tests/api/test_research.py` must fail on the old code and cover:
route/model existence, PIT filtering, parameter dictionaries, selected columns
(no `SELECT *`), metric/symbol/limit rejection, five-peer and graph hard caps,
partial/missing peer behavior, graph truncation/provenance, safe warehouse
failure messages, and distinct empty/stale/unavailable lineage states. Named
mutations: remove the as-of predicate; string-interpolate symbol; allow an
unknown metric; remove graph caps; turn missing peer values into zero; report a
missing table as empty; and leak the connector exception. Run:

```sh
pytest -q tests/api/test_research.py tests/api/test_public_demo_security.py tests/api/test_resilience.py
```

## 4. Build rounds

Every round follows the owner workflow: MiMo build, DeepSeek check, Codex
review, Claude review, then PR and CodeRabbit. Each BUILD request must require
LF line endings, no edits to `.agents/dispatch.sh`, a commit, a written MiMo
verdict, failing-before proof on a pre-slice `/tmp` worktree/copy, and named
mutation evidence from the checker.

Unless a round says otherwise, frontend acceptance is:

```sh
cd frontend && npm ci && npm test -- --run && npx tsc --noEmit && npm run build
```

### B1 — Company Facts bronze/silver/gold lane

- **Files:** `pipelines/ingest_sec_companyfacts.py`, a silver XBRL transform
  under `silver/`, a gold transform under `gold/`, alias registry/config,
  `pipelines/run_silver_gold.py`, `resources/jobs.yml`, schema-contract/docs,
  and the three test files in section 2.5.
- **Source:** SEC Company Facts plus acceptance timestamps from
  `bronze_sec_filings_v2`; output is the three tables in section 2.
- **States:** successful, partial ticker failure with manifest, rate-limited
  retry exhausted, malformed fact quarantined, unresolved accession, empty
  issuer facts, and idempotent rerun.
- **Tests that fail now:** all ten section 2.5 behaviors; none of the dedicated
  tables or job tasks exist on the current branch.
- **Named mutations:** all section 2.5 mutations.
- **Acceptance:** the backend commands in section 2.5 plus the repository's
  job/schema validation tests.

### B2 — Typed research APIs

- **Files:** `api/schemas.py`, `api/routes/research.py`, `api/routes/__init__.py`,
  `api/main.py`, narrow query helpers in `db/delta_adapter.py`,
  `frontend/src/api/types.ts`, `frontend/src/api/client.ts`, and
  `tests/api/test_research.py`.
- **Source:** `gold_fundamentals_quarterly`, `silver_sec_entities`,
  `silver_sec_sections`, allowlisted table metadata, and existing OHLCV only
  where the frontend later requests it separately.
- **States:** populated, empty, stale, partial, unavailable, invalid request,
  unknown root, and truncated graph.
- **Tests that fail now:** every endpoint and type in section 3 is absent.
- **Named mutations:** all section 3 mutations, plus a response model/frontend
  type field removed on only one side.
- **Acceptance:** API commands in section 3 and frontend acceptance.

### B3 — Fundamentals and price chart

- **Files:** add `frontend/src/components/charts/FundamentalsPriceChart.tsx` and
  its test; update the A5-owned `frontend/src/screens/MarketDashboard.tsx`
  **only after A5 is merged**, plus API client/types if B2's handoff requires
  reconciliation.
- **Source:** fundamentals endpoint for one or two selected metrics and the
  existing `/api/market/{symbol}` OHLCV envelope. Align observations by date,
  but keep separate labelled axes/units; never imply a causal relationship.
- **UI:** metric selector, quarterly/annual selector, optional split-adjusted
  close overlay, accessible tabular fallback, accession/source disclosure, and
  no chart dependency initially. Use responsive SVG/CSS with point count caps.
- **States:** loading skeleton, fundamental empty with price still visible,
  price empty with fundamentals visible, stale notice retaining data, partial
  series/gaps, unavailable retry, and populated.
- **Tests that fail now:** renders filed quarterly values and price overlay;
  switches frequency without mixing series; uses acceptance/source provenance;
  retains one source when the other is empty; renders null as a gap, not zero;
  and exposes a table/labels at 360 px.
- **Named mutations:** use report date as availability; plot null as zero; put
  USD and percent on one unlabelled scale; hide stale data; remove fallback
  table; and import Recharts/React Flow.
- **Acceptance:** frontend acceptance plus `pytest -q tests/api/test_research.py tests/api/test_market.py`.

### B4 — Peer comparison

- **Files:** add `frontend/src/screens/PeerComparison.tsx` and test; update
  `frontend/src/App.tsx`/navigation only after A3–A5 handoffs are stable; use
  B2 client/types.
- **Source:** `/api/research/peers`; explicit 2–5 symbols from the shared A5
  `SymbolPicker`, one canonical metric and one as-of date.
- **UI:** comparable-value bars/table, missing-value rows, unit and fiscal
  period warnings, accession links, and disclosed peer-set origin.
- **States:** loading, fewer than two symbols, empty all, partial peers,
  incompatible unit, stale, unavailable, and populated.
- **Tests that fail now:** compares explicit symbols; caps selection at five;
  preserves unavailable peer rows; does not rank incomparable units; changes
  metric/as-of via encoded parameters; and renders provenance.
- **Named mutations:** silently add a competitor; drop a missing peer; rank
  null as zero; compare different periods without warning; remove the cap; and
  omit accession provenance.
- **Acceptance:** frontend acceptance plus `pytest -q tests/api/test_research.py`.

### B5 — Bounded knowledge-graph explorer

- **Files:** add `frontend/src/screens/KnowledgeGraphExplorer.tsx`,
  `frontend/src/components/graph/LightweightGraph.tsx`, and tests; update
  navigation/App after the A slices; use B2 client/types.
- **Source:** `/api/research/graph/neighbourhood`; selection opens accession,
  accepted timestamp, source section/excerpt link where supplied.
- **UI:** one symbol/root, typed legend, node/edge counts, server-driven
  one-hop expansion, truncation notice, keyboard-selectable node list/table,
  and SVG/canvas visual enhancement. No React Flow and no client force layout
  over unbounded records.
- **States:** loading, empty, stale, unavailable, truncated, selected evidence
  unavailable, and populated.
- **Tests that fail now:** requests bounded defaults; expands via a second
  bounded API request; shows truncation; opens source evidence; keyboard
  selection works without the canvas; and no prohibited dependency is present.
- **Named mutations:** request all entities; ignore `truncated`; use array index
  IDs; render a causal label for co-occurrence; remove keyboard fallback; and
  add `@xyflow/react`.
- **Acceptance:** frontend acceptance plus `pytest -q tests/api/test_research.py`.

### B6 — Architecture lineage flow

- **Files:** update A3's `frontend/src/screens/ArchitectureEvidence.tsx` only
  after A3 is approved; add `frontend/src/components/LineageFlow.tsx` and tests.
- **Source:** declared diagram from A3 plus `/api/research/lineage` observed
  table states. The diagram remains useful when the endpoint is unavailable.
- **UI:** HTML/CSS nodes for SEC Company Facts → bronze XBRL → silver facts →
  gold fundamentals → typed API → charts/agent, alongside the broader A3
  architecture. Show generated-at and measured timestamps; no animated
  “running” edges.
- **States:** static-only/unavailable, empty table, stale table, partial node
  status, and populated.
- **Tests that fail now:** includes the full XBRL lineage; distinguishes empty
  from unavailable; does not invent running state; retains static architecture
  on failure; and stays overflow-safe at 360 px.
- **Named mutations:** display unavailable as healthy; label empty count as a
  live success; remove generated-at; animate an unobserved running job; and
  omit the acceptance-time node/detail.
- **Acceptance:** frontend acceptance plus `pytest -q tests/api/test_research.py`.

### B7 — Filing tone and risk-change panel

- **Files:** add `api/routes/filing_insights.py` or a small addition to the B2
  research route, Pydantic/types/client contract, add
  `frontend/src/components/filings/FilingInsightsPanel.tsx` and tests, and
  integrate into `SecFilingExplorer.tsx` after A5 and A4 evidence handoffs.
- **Source:** named columns from `gold_sec_features`, keyed by ticker/accession,
  ordered by `information_available_ts`; expose positive, negative,
  uncertainty, `risk_factor_change`, `filing_similarity`, form, accession and
  accepted timestamp. Do not generate a narrative summary or confidence.
- **States:** no prior filing (change unavailable), empty, stale, unavailable,
  partial metrics, and populated. Explain that counts/rates are deterministic
  lexicon indicators, not investment sentiment or model confidence.
- **Tests that fail now:** renders exact stored metrics; shows no-prior state;
  keeps stale data visible; provenance identifies both compared filings; null
  change is not zero; and API SQL is parameterized/PIT-bounded.
- **Named mutations:** replace null with zero; label the score as confidence;
  compare to a later filing; use filing date instead of acceptance time; omit
  prior accession; and fabricate key drivers.
- **Acceptance:** frontend acceptance plus focused API tests and
  `pytest -q tests/rag/test_sentiment.py tests/gold/test_pit_leakage.py`.

### B8 — Tours for new screens

- **Files:** update `frontend/src/components/tours/tourSteps.ts` and
  `TourHost.tsx`; add targets to B3–B7 screens and extend existing tour tests.
- **Source:** mounted UI only. Add keys such as
  `qp_tour_fundamentals_v1`, `qp_tour_peers_v1`,
  `qp_tour_knowledge_graph_v1`, and `qp_tour_filing_insights_v1`.
- **Behavior:** replay from the existing header, one auto-run per versioned
  key, reduced-motion rule, focus trap/restore, Escape/arrows, and centered
  fallback for a missing target. Tours explain PIT/as-of, source provenance,
  graph truncation and deterministic tone methodology.
- **States:** targets present, target absent because data is empty, mobile,
  reduced motion, previously completed, and explicit replay.
- **Tests that fail now:** new keys/steps/targets do not exist; add one test per
  tour plus a route-change/missing-data case.
- **Named mutations:** reuse an existing key; target a styling class; block on
  empty-data target; auto-run under reduced motion; lose opener focus; or let a
  cross-screen step remain pointed at an unmounted node.
- **Acceptance:** frontend acceptance, especially the existing CoachMarks and
  TourHost suites.

### B9 — Optional read-only agent fundamentals tool (separate scope)

This is optional and must not block B1–B8. Add only after B2 is stable and PR
#39's agent changes are merged/reconciled.

- **Files:** existing agent tool schema/registry, validator/allowlist and
  runtime, tests, plus A4 `ToolCallCard` rendering after A4 lands.
- **Contract:** `get_fundamentals(symbol, metrics, frequency, as_of)` calls the
  same bounded deterministic query helper as the REST endpoint. It is
  read-only, maximum six metrics/40 points, validates symbol and enum values,
  and returns values with acceptance timestamp/accession/source concept.
- **States:** populated, empty, stale warning, unavailable, validation failure,
  and runtime failure. It must not fetch SEC over HTTP at request time and must
  not write data.
- **Tests that fail now:** tool absent; validator rejects non-allowlisted
  metrics and extra arguments; runtime uses bounded parameterized query; tool
  result carries provenance; failed/unavailable tool is rendered honestly.
- **Named mutations:** bypass validator; interpolate symbol; remove point cap;
  issue Company Facts HTTP from the API request; drop accession/as-of; or mark
  an unavailable result `ok=true`.
- **Acceptance:** focused agent tests, `pytest -q tests/agent tests/api/test_agent_chat_llm.py`, and frontend acceptance if A4 cards change.

### B10 — Read-only agent action audit browser

- **Files:** add a typed, read-only route such as `api/routes/audit.py` and its
  Pydantic/frontend contracts; add `frontend/src/screens/AuditLog.tsx` and
  focused API/UI tests; update `frontend/src/App.tsx` and Evidence navigation
  only after A4 and the application-shell handoff are stable. Do not import the
  Rag_workbench review schema, review queue, DuckDB database, or mutation APIs.
- **Source:** the existing Lakebase `agent_actions` audit records emitted by
  `agent/runtime.py` and `agent/tools_write.py`, scoped to the authenticated
  user unless an explicitly authorized operator role exists. Select an
  allowlisted summary projection: run/action ID, timestamp, tool, action type,
  sanitized input/output summary, status, error category and trace/correlation
  ID. Never return prompts, credentials, raw connector errors, or other users'
  records. Use cursor pagination, deterministic newest-first ordering and
  allowlisted status/tool filters; no review or approval action belongs here.
- **States:** loading, empty, populated, filtered-empty, next-page loading,
  stale retained after refresh failure, unavailable, malformed/redacted legacy
  row, and unauthorized.
- **Tests that fail now:** the route and screen do not exist; tests must prove
  user scoping, parameterized queries, stable cursor pagination, allowlisted
  filters, redaction/truncation, safe errors, empty versus unavailable UI,
  accessible row expansion, and no review/mutation controls at 360 px.
- **Named mutations:** remove the `user_id` predicate; interpolate a filter;
  return raw input/output or exception text; sort oldest-first; replace the
  cursor with an unbounded query; turn unavailable into empty; add an approve
  button; or query `review_queue.duckdb`.
- **Acceptance:** frontend acceptance plus focused audit API tests and the
  existing agent runtime/write audit tests.

### B11 — Legal and analytics-transparency surfaces

- **Files:** add `frontend/src/screens/Privacy.tsx` and `Terms.tsx`, a small
  shared legal layout/footer, and an analytics notice only if telemetry is
  actually enabled; add route/navigation links and focused tests. Legal text
  must be owner/counsel-approved configuration or copy, not copied verbatim
  from Rag_workbench and not invented by the implementer.
- **Source:** static approved policy content plus the deployed telemetry and
  authentication configuration. The notice must describe only collection that
  can be verified in this repository/deployment and link to the matching
  policy. It is informational, accessible and non-blocking; it is not an
  investment-advice acceptance gate.
- **States:** telemetry disabled (no analytics notice), first visit, dismissed
  notice, storage unavailable, direct legal-route load, missing/unapproved
  policy content (route withheld), mobile and print-friendly legal content.
- **Tests that fail now:** legal routes/layout and telemetry-aware notice do not
  exist; tests must prove footer links, semantic headings, keyboard dismissal,
  versioned acknowledgement, safe storage failure, no notice when telemetry is
  off, no false advertising/privacy claim, and 360 px/print readability.
- **Named mutations:** show the notice when telemetry is disabled; hard-code a
  claim contradicted by configuration; make acknowledgement blocking; swallow
  keyboard focus; reuse a disclaimer key; publish placeholder legal text; or
  omit policy links from the application shell.
- **Acceptance:** frontend acceptance plus a repository/configuration check
  that every described telemetry field/provider is real and enabled. Owner or
  counsel approval of the final policy copy is a release gate, not a test the
  implementation agent may waive.

## 5. Ordering and dependencies

The build order is:

```text
A2 r3 check/review → A3 → A4 → A5
                         │      │
B1 XBRL data → B2 APIs ──┘      │
                 ├→ B3 chart (after A5)
                 ├→ B4 peers (after A5/App handoff)
                 ├→ B5 graph (after App handoff)
                 └→ B6 lineage (after A3)
gold_sec_features ─────────→ B7 filing insights (after A4/A5)
B3–B7 mounted targets ─────→ B8 tours
B2 + A4 + agent PR #39 ────→ B9 optional agent tool
A4 + Lakebase audit contract ─→ B10 audit browser
approved policy + telemetry config ─→ B11 legal/transparency
```

- The current branch contains A1 and A2 round-three remediation, with a
  DeepSeek check request at `2b06608`. Do not start A3 until that check and the
  required Codex/Claude reviews approve A2.
- A3–A5 remain pending. B1 can be built in a separate backend-only worktree
  after the current UI sequence is safely isolated, but B2 must be reconciled
  with any API/type edits before frontend rounds. B3 must wait for A5 because
  both touch `MarketDashboard`, shared symbol selection and API types. B6 must
  wait for A3's Architecture file. B7 must wait for A4/A5 because it extends
  their evidence/SEC screen handoffs. B8 comes last so its selectors name final
  mounted elements.
- PR #28 is the universe-wide SEC ingest dependency documented locally as 557
  tickers pending rollout, while the live retrieval snapshot covers 16. B1
  should read the canonical configured SEC-covered universe and be safe on the
  currently ingested subset; do not claim 557-ticker fundamentals coverage
  until PR #28 is merged and the jobs have run. Rebase/reconcile its universe,
  CIK mapping, ingest manifest and SEC rate-limit conventions before B1 review.
- PR #39 is an in-flight agent change. B1–B8 do not depend on its runtime
  behavior. Reconcile B9 only after it lands so the new tool uses the final
  validator/allowlist and retry semantics rather than forking them.
- GitHub was not reachable while this plan was authored, so PR state/title was
  not guessed; the dependencies above use the owner request and repository
  evidence. The coordinator must refresh both PR states before dispatch.
- Every round has exclusive ownership of shared files. In particular, do not
  run A3 and B6, A4 and B7/B9, A5 and B3/B4/B7, or B2 and any frontend slice
  that edits API types/client at the same time.
- B10 waits for A4 so its evidence vocabulary and action identifiers are
  stable, and for the Lakebase audit schema to be confirmed; it is read-only
  and is not a review queue. B11 can proceed after the app-shell routes settle,
  but final copy must wait for owner/counsel approval and verified telemetry
  configuration. Neither slice blocks B1–B9.

The agent gains a useful, auditable read path only in B9: questions can request
canonical filed fundamentals as of a stated time, and the answer can cite the
accession/concept. It gains no write authority, no arbitrary SQL, no new graph
orchestration framework, and no permission to treat baseline signals as an
edge.

## 6. Risks and controls

| Risk | Control / acceptance evidence |
| --- | --- |
| Company-specific concept aliases and taxonomy evolution | Versioned canonical alias registry, effective-dated company overrides, source concept on every output, unknown concepts flagged and measured rather than silently mapped. |
| Units, decimals, and scale | Retain raw unit/value, normalize only allowlisted compatible units, never guess scale, test USD/shares/USD-per-share separation and extreme values. |
| Fiscal calendars and 52/53-week years | Use SEC fiscal metadata and context duration; do not map calendar month directly to fiscal quarter; test a non-calendar filer and 53-week period. |
| Amended filings and comparative-period restatements | Keep every accession, key PIT availability to SEC acceptance, choose the latest accepted value at `as_of`, and mutation-test oldest/newest ordering. |
| Company Facts lacks full segment/geography dimensions | Populate only explicit source dimensions with provenance; otherwise return unavailable flags, never narrative estimates. |
| Acceptance timestamp absent from Company Facts | Resolve by accession against filing bronze; quarantine/unpublish unresolved facts and backfill, never substitute filed date or ingest time. |
| Duplicate Company Facts entries/frames | Exact-ingest dedupe with accession/context identity; deterministic priority and quality flags for conflicting values. |
| Partial issuer coverage and delayed rollout | Honest covered/empty/partial states, per-ticker ingest manifest, no 557-ticker claim before PR #28 rollout evidence. |
| SEC throttling/blocking | Required identity, process-wide rate cap, Retry-After/backoff, bounded concurrency and retries, run-level cache/manifest. |
| PIT leakage into charts, peers, or agent | Shared as-of query helper, mandatory acceptance predicate, old-code and mutation proofs, provenance echoed in every point. |
| Graph size and misleading relationships | Server-side node/edge/depth caps, deterministic truncation, evidence-backed relation vocabulary, accessible list fallback. |
| Chart bundle size | Start with native SVG/CSS and capped points; record Vite bundle sizes before/after. Any chart library requires a separate size/accessibility justification and must be lazy-loaded. |
| Overlapping A/B edits | Sequential ownership and explicit handoffs described above; rebase and rerun full acceptance after each shared-file reconciliation. |
| “Live” status fabrication | Lineage exposes only measured row/timestamp state and generated-at; no pending/running animation without a real job-run contract. |
| Tone score misinterpretation | Label deterministic lexicon/risk-change methodology, preserve null/no-prior states, and never call it confidence or investment sentiment. |

## Definition of done for Plan B

Plan B is complete only when each dispatched slice has its required check and
reviews, the new tests have demonstrated failure on old code and named mutation
survival, PIT behavior is proved with amendment fixtures, all UI states are
honest and accessible at 360 px, frontend bundle impact is recorded, and the
coordinator has verified the actual merge/rollout state of PRs #28 and #39.

## 7. Gap audit (2026-10-06)

The rows below cover every page, component and service named in the audit
request. `ALREADY-COVERED` means qp1 already has an implementation or a binding
A/B slice owns the useful behavior; it does not authorize importing the legacy
module. A matching filename is not sufficient when its runtime depends on a
prohibited architecture.

| Rag_workbench item | What it does in Rag_workbench | quant_platform_1 equivalent | Decision | Reason |
| --- | --- | --- | --- | --- |
| Page `PortfolioHome` | Personal portfolio landing page with project cards, profile/contact links and a tour. | `frontend/src/screens/PlatformOverview.tsx` (A3, planned) and `frontend/src/layout/AppShell.tsx` | **ALREADY-COVERED** | A3 supplies the product landing/evidence narrative; personal-brand chrome is outside the research application. |
| Page `StocksList` | Static card list of covered companies and filing-range caveats. | `frontend/src/data/symbols.json` and `frontend/src/components/SymbolSelect.tsx`; A5 `SymbolPicker` | **ALREADY-COVERED** | A5 owns data-backed coverage, validation and no-coverage messaging; do not copy a hard-coded universe. |
| Page `AuditLog` | Fetches audit runs and summary counts, filters them and expands lineage, verification and error detail. | `agent/runtime.py`, `agent/tools_write.py`; no read-only browser | **ADAPT** | B10 exposes a user-scoped, redacted Lakebase action history without the prohibited review queue or DuckDB. |
| Page `ProductAnalytics` | Displays product-use KPIs and charts from server/PostHog summaries. | `api/routes/analytics.py`, `pipelines/lakebase_analytics.py`; A-phase `ActivityAnalytics.tsx` | **ALREADY-COVERED** | The binding analytics screen uses materialized measured data and honest empty/stale states. |
| Page `Presentation` | Static case-study slide deck describing the workbench. | A3 `PlatformOverview.tsx` and `ArchitectureEvidence.tsx` (planned) | **SKIP** | A duplicate presentation route adds maintenance and risks stale or fabricated claims. |
| Page `ConjointStudy` | Shows conjoint experiment results, attribute utilities, role segments and usefulness votes. | none | **SKIP** | Product research/experimentation is not a required research-platform capability and its data contract is absent. |
| Page `Privacy` | Long-form privacy policy in a shared legal shell. | none | **KEEP** | B11 adds an approved policy surface tied to actual telemetry/deployment behavior. |
| Page `Terms` | Long-form terms and investment-risk limitations in a shared legal shell. | none | **KEEP** | B11 adds approved terms without treating a disclaimer acknowledgement as authorization or safety control. |
| Component `MarkdownMessage` | Renders a restricted subset of Markdown with GFM tables and safe links. | A4 grounded-answer/evidence rendering in `frontend/src/screens/ResearchAgent.tsx` (planned) | **ALREADY-COVERED** | A4 owns readable answers and collapsed developer detail; any renderer must stay sanitized and evidence-first. |
| Component `DataTable` | Renders parsed Markdown table headers/rows with alignment and numeric styling. | `frontend/src/components/Table.tsx`; B3 accessible chart table fallback | **ALREADY-COVERED** | Reuse the native table primitives rather than add a second chat-specific table system. |
| Component `ChartErrorBoundary` | Catches chart render exceptions and shows a compact fallback. | B3 chart unavailable/error state and accessible table fallback | **ALREADY-COVERED** | B3 already requires independent source failure handling; its implementation may use a local boundary without a separate slice. |
| Component `Disclaimer` | Blocking acknowledgement modal plus persistent informational footer. | none; B11 legal footer | **ADAPT** | Keep non-blocking, approved disclosures in B11; a local-storage gate is not consent, suitability or investment protection. |
| Component `LegalLayout` | Shared privacy/terms header, navigation, prose primitives and footer. | none | **KEEP** | B11 needs a small accessible shared layout, with qp1 navigation and approved copy. |
| Component `AnalyticsNotice` | One-time dismissible notice describing anonymous analytics and linking to privacy. | none | **ADAPT** | B11 shows it only when verified telemetry is enabled and makes claims match configuration. |
| Component `ConjointGate` | Lets a visitor self-select control/treatment and a professional role. | none | **SKIP** | Role experiment assignment would personalize output without a qp1 product requirement or evaluation contract. |
| Component `ConjointSurvey` | Runs choice tasks, records preferences and collects a usefulness vote. | none | **SKIP** | It requires the out-of-scope conjoint backend and introduces user-study writes unrelated to governed research. |
| Service `peer_comparison` | Detects comparison intent, resolves peers and computes filing-derived comparison tables. | `api/services/peer_comparison.py`; B2/B4 replace its implicit-peer behavior | **ALREADY-COVERED** | B4 requires explicit 2–5-symbol sets, canonical metrics, PIT provenance and honest missing values. |
| Service `financial_calc` | Computes ratios/identities with structured calculation audit trails. | `api/services/financial_calc.py`; B1 canonical derived metrics | **ALREADY-COVERED** | The useful deterministic math exists; B1 tightens period, unit, sign and PIT rules for published fundamentals. |
| Service `chart_tool` | Detects chart requests and builds annual/quarterly chart specifications. | `api/services/chart_tool.py`; B3 typed chart | **ALREADY-COVERED** | B3 uses bounded typed endpoint data rather than trusting an agent-created arbitrary chart payload. |
| Service `confidence_scorer` | Assigns confidence/routing tiers from validation triggers and calibrated cut points. | `api/services/confidence_scorer.py` | **SKIP** | Do not expose or newly integrate arbitrary confidence scores; deterministic reason codes may remain internal. |
| Service `calibration` | Recalculates confidence thresholds from labelled outcomes. | `api/services/calibration.py` | **SKIP** | No approved labelled evaluation/calibration lane is specified, and it depends on the prohibited scoring/review design. |
| Service `verifier` | Combines schema/semantic checks and optional Polygon corroboration into a verification result. | `api/services/verifier.py`; A4 tool/source status | **ALREADY-COVERED** | The existing qp1 verifier can support grounded status, but B screens must not add Polygon or claim certainty. |
| Service `semantic_validator` | Checks identities, referential consistency and numeric plausibility. | `api/services/semantic_validator.py` | **ALREADY-COVERED** | Deterministic validation is already present and is preferable to UI confidence decoration. |
| Service `schema_validator` | Validates extraction fields, accession/CIK formats, units and suspicious scale. | `api/services/schema_validator.py` | **ALREADY-COVERED** | Existing validation plus B1's unit/PIT tests covers the useful behavior. |
| Service `polygon_verifier` | Fetches Polygon company/financial data and cross-checks extracted figures/auditors. | `api/services/polygon_verifier.py` | **SKIP** | OWNER_PLAN still forbids Polygon panels/integration in this lane; lifting XBRL/graph did not lift Polygon. |
| Service `drift_detection` | Calculates agreement/concept-spike drift status and logs alerts. | `api/services/drift_detection.py`; Plan B inventory `DriftAlert` decision | **SKIP** | No materialized measured drift contract exists, so defaults could be presented as observations. |
| Service `metric_router` | Routes named metric requests through deterministic fact calculations. | `api/services/metric_router.py`; B1/B2 canonical metrics | **ALREADY-COVERED** | Keep deterministic helpers, while B1/B2 add reviewed aliases, units, PIT selection and API allowlists. |
| Service `graph_rag_engine` | Uses a LangGraph workflow to extract entities, query a graph and generate an answer. | `api/services/graph_rag_engine.py`; B5 read-only neighbourhood only | **SKIP** | LangGraph orchestration and generated graph answers remain prohibited; B5 is bounded evidence exploration. |
| Service `rag_engine` | Combines Polygon, DuckDB vectors, EDGAR embeddings/facts and price context in a LangChain RAG chain. | `agent/tools_retrieval.py` for governed retrieval; no direct port | **SKIP** | It depends on DuckDB, Polygon and an untyped chain; the native agent retrieval contract is the supported path. |
| Service `chat_engine` | Generates, validates and executes LLM-written DuckDB SQL, then summarizes results. | `api/services/chat_engine.py` exists as legacy code; typed qp1 routes/agent tools are the supported equivalent | **SKIP** | Free-form SQL chat and DuckDB are expressly prohibited even though the legacy file is present. |
| Service `langgraph_engine` | Orchestrates retrieval, extraction, math, verification, evaluation, output and DuckDB audit nodes. | `api/services/langgraph_engine.py` exists as legacy code; `agent/runtime.py` is the governed runtime | **SKIP** | Do not extend the LangGraph/DuckDB workflow; use typed schemas, allowlists and deterministic execution. |
| Service `shadow_runner` | Runs a non-blocking comparison pipeline and derives calibration recommendations. | `api/services/shadow_runner.py` | **SKIP** | It feeds the unapproved confidence calibration/review workflow and has no B-slice product requirement. |
| Service `runtime_snapshot` | Uploads/restores the DuckDB review database as a remote snapshot. | `api/services/runtime_snapshot.py` | **SKIP** | B slices use Lakebase/Delta and must not preserve or revive `review_queue.duckdb`. |
| Service `llm_health` | Tracks recent LLM success/failure/latency in process memory. | `api/services/llm_health.py`; A-phase `SystemHealth.tsx` | **ALREADY-COVERED** | System Health owns truthful service state; in-memory observations must be labelled and not presented as durable history. |
| Service `sec_analyzer` | Uses an LLM to extract filing entities, risks and forward-looking statements. | `api/services/sec_analyzer.py`; `silver_sec_entities` and B5/B7 | **ALREADY-COVERED** | B5 consumes persisted evidence-backed entities and B7 stored deterministic features, not request-time invented claims. |
| Service `edgar_adapter` | Fetches a filing and converts XBRL/HTML facts into extraction fields. | `api/services/edgar_adapter.py`; B1 Spark Company Facts lane | **ALREADY-COVERED** | The helper exists, while B1 defines the governed batch source, identity, manifest and PIT publication rules. |
| Service `sec_client` | Reads SEC facts/filing sections from the local workbench database. | `api/services/sec_client.py`; B1 tables and B2 typed routes | **ALREADY-COVERED** | B1/B2 replace request-path/local-store assumptions with Delta-backed, bounded contracts. |
| Service `embeddings` | Selects hosted or local embedding implementations. | `api/services/embeddings.py`; `pipelines/build_sec_embeddings.py` | **ALREADY-COVERED** | Embedding construction already exists; this audit adds no alternate model or storage path. |
| Service `reranker` | Reorders retrieved documents with a cross-encoder and falls back to original order. | `api/services/reranker.py`; `agent/tools_retrieval.py` | **ALREADY-COVERED** | Retrieval/reranking is already part of the native evidence path and needs no UI slice. |
| Service `hybrid_retriever` | Combines BM25 and vector results with RRF and ticker/accession metadata. | `api/services/hybrid_retriever.py`; `agent/tools_retrieval.py` | **ALREADY-COVERED** | Governed retrieval already covers the useful hybrid behavior; A4 surfaces its provenance. |
| Service `_edgar_identity` | Validates and installs a non-placeholder SEC User-Agent. | `api/services/_edgar_identity.py`; B1 SEC client requirements | **ALREADY-COVERED** | B1 explicitly requires this identity behavior, rate limiting, retry policy and tests. |
