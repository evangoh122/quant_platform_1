# Public natural-language analytics v1 plan

## Outcome

Build a public portfolio application that answers bounded natural-language
questions over 200M+ governed market records. The LLM resolves ambiguity into a
typed intent; deterministic code validates policy, compiles SQL, executes it,
validates results, and records provenance.

The public claim is deliberately precise:

> Every answer records the semantic model, SQL, dataset version, statement ID,
> and trace ID required for reproducibility within source-retention limits.

## Coordination and non-interference gate

Before implementation, refresh the dependency and ownership map against the
current default branch and open pull requests. Do not rely on historical lane,
branch, or worktree status recorded in planning documents. Repository workflow,
validation, and pull-request requirements are defined only in root `AGENTS.md`.

## V1 architecture

```text
Render Static Site (React)
        |
        | HTTPS + SSE
        v
Render Starter Web Service (one FastAPI process)
        |
        | OAuth M2M + Statement Execution API
        v
Databricks SQL Warehouse (2X-Small, max clusters 1)
        |
        +-- Unity Catalog approved views
        +-- Gold aggregate tables
        +-- bounded Silver drill-down tables
```

Use one backend replica in v1. In-process rate limiting, cache, daily counters,
single-flight, and a global warehouse semaphore are intentional constraints,
not claims of horizontally scalable infrastructure. Do not add Redis, Kafka,
Kubernetes, a vector database, or server-side conversation storage.

### Dataframe responsibilities

- PySpark builds and maintains Bronze/Silver/Gold Delta tables in Databricks.
- Polars supports local research and bounded offline analysis.
- Pandas is restricted to library boundaries that require it.
- The Render request path uses the Statement Execution REST API and bounded JSON
  results; it does not run Spark, Polars, or pandas over the 200M-row source.

## Request pipeline

Use a small typed async pipeline, not LangGraph:

```text
question
  -> intent extraction (LLM call 1)
  -> deterministic entity resolution
  -> slot and policy validation
  -> deterministic semantic SQL compiler
  -> Statement Execution API
  -> deterministic result validation
  -> grounded answer and constrained chart schema (LLM call 2)
```

Create an OpenTelemetry span for each stage. Stream stage events with SSE. If
the stream disconnects, the client reruns the request; v1 has no resumable event
protocol.

Conversation context remains client-side and untrusted. A follow-up sends only
the previous canonical intent and the new question. The server validates both.

## Semantic contract

The LLM may produce only a versioned structured intent. It may not emit SQL,
table names, predicates, ordering expressions, or code.

Initial metrics:

1. price
2. return
3. volume
4. realized volatility
5. drawdown
6. momentum
7. market capitalization
8. relative performance

Initial operations: `trend`, `compare`, `rank`, and `aggregate`.

The compiler owns a registry mapping each approved metric/operation pair to:

- an approved Gold or Silver view;
- fixed columns and aggregation expression;
- required entity/date slots;
- allowed grouping and ordering;
- parameter types and bounds;
- output schema and chart families;
- semantic-model version.

SQL uses bound parameters wherever supported. Identifiers come only from the
registry. There is no generated-SQL repair loop and no unrestricted table
selection.

## Entity resolution and ambiguity

Use a deterministic, versioned alias registry for tickers, company names,
sectors, indices, macro series, units, and relative dates. Include every
resolution in the trace, for example `"Google" -> GOOGL`.

Do not expose uncalibrated LLM confidence numbers. Validate required slots. If
a safe default exists, apply it and disclose the assumption; otherwise reject
or ask a narrowly scoped clarification.

## Query policy

Classify canonical intent before SQL compilation as `CHEAP`, `NORMAL`,
`EXPENSIVE`, or `REJECT`.

| Layer | Required scope | Date bound | Ticker bound | Row bound |
|---|---|---:|---:|---:|
| Gold | metric + operation | 10 years | registry-defined | 5,000 |
| Silver | ticker/entity + dates | 2 years | 10 | 10,000 |

Intraday queries are outside v1 because no intraday serving source is currently
identified. Market capitalization is also conditional on adding a governed
shares-outstanding/market-cap source; otherwise substitute an available eighth
metric before freezing NL1.

Enforce bounds in the intent validator, generated SQL, Statement API
`row_limit`/`byte_limit`, and result validator. A rejected request emits no SQL
and makes no warehouse call. Optimize serving tables with Liquid Clustering;
do not make Z-order the primary design.

## Databricks execution

Use OAuth M2M with a service principal granted warehouse use plus `SELECT` on
dedicated serving views only. Never place a PAT in Render.

Before NL3 freezes its contract, verify in the actual workspace whether the
Statement Execution and Query History APIs support the intended query-tag,
`byte_limit`, `on_wait_timeout`, cancellation, and `include_metrics` behavior.
Do not promise fields that have not been observed. If per-statement query tags
are unavailable, include the trace ID in a sanitized SQL comment and correlate
by `statement_id`.

For each accepted request:

1. attach query tags containing application, trace ID, cost class, semantic
   version, operation, and metric;
2. submit through the Statement Execution API;
3. retain `statement_id` immediately;
4. poll asynchronously with a hard timeout;
5. cancel on timeout or client cancellation where safe;
6. reject oversized or schema-invalid output;
7. release the global semaphore in a `finally` block.

Start load testing at concurrency 2, 4, 6, 8, and 10. Select the production
semaphore value from p50/p95 latency, memory, event-loop lag, warehouse queue
time, SSE failures, and LLM latency—not from an assumption.

## Cache and cost controls

Use two explicitly reported cache layers: application cache and Databricks
result cache. The application key is a stable hash of:

```text
canonical intent
+ semantic model version
+ dataset version
+ policy version
```

Add single-flight per cache key to prevent a miss stampede. Cached requests
should not wake the warehouse. Use bounded TTL/LRU storage, a daily in-memory
query counter, per-IP limits, Turnstile verification, LLM token caps, a provider
hard spending limit, one warehouse cluster, and short auto-stop. The daily
counter is a supplementary guard because a Render restart resets it.

## Provenance and telemetry

Return reliable fields with the answer:

- statement ID and sanitized deterministic SQL;
- canonical intent and semantic-model version;
- dataset/version or snapshot identifier;
- policy version and query cost class;
- rows returned and backend-measured runtime;
- application-cache status;
- trace ID.

After the answer is delivered, poll Query History by `statement_id` with
`include_metrics=true` after approximately 2, 3, and 5 seconds. Backfill only
fields verified in the actual workspace. Keep missing telemetry explicitly
pending/unavailable and measure its observed p50/p95 availability latency.

Dataset version comes from a scheduled, validated serving-data manifest. Do
not run `DESCRIBE HISTORY` or other metadata scans on each visitor request.

## Frontend contract

The React UI contains:

- question input and suggested questions;
- grounded answer and constrained chart renderer;
- expandable execution-stage trace;
- provenance panel with copyable SQL and identifiers;
- explicit assumptions, policy rejections, busy states, and cache-layer state;
- architecture-rationale page;
- two flagship examples: 200M-to-small-result and adversarial rejection.

The chart schema is a discriminated union of approved chart types, axes, series,
labels, and bounded data references. The frontend never executes model-produced
JavaScript, HTML, formatter functions, or URLs.

### Business, IT, and testing showcase page

After the current README update is complete and integrated, add a dedicated
portfolio showcase page. Before implementation, compare the final README diff
and current frontend ownership so the page does not overwrite that content or
collide with an active UI lane.

The page tells one connected story through three expandable sections.

**Business logic**

- the visitor problem and target users;
- why governed natural-language analytics is valuable over 200M+ records;
- supported question types, explicit assumptions, and useful defaults;
- query rejection and cost-control behavior;
- the 200M-to-small-answer and adversarial-rejection demonstrations;
- measurable outcomes, limitations, and deferred v1.1 scope.

**IT logic**

- structured intent extraction and deterministic entity resolution;
- slot validation, query policy, and cost classification;
- semantic registry and deterministic SQL compilation;
- OAuth M2M Statement API execution and least-privilege serving views;
- concurrency, cache layers, timeouts, cancellation, and SSE stages;
- OpenTelemetry, query tags, Query History backfill, and provenance;
- trust boundaries across browser, Render, Databricks, LLM, and telemetry.

**Tests and evidence**

- golden-set intent/entity/policy/SQL/numerical/chart results;
- RAG retrieval metrics and zero-PIT-leakage gate;
- security and adversarial tests, including no-SQL rejection;
- cache, timeout, cancellation, route, secret, and write-boundary tests;
- load-test results used to choose the semaphore value;
- accessibility/mobile checks and known limitations.

Interactive elements may include an expandable execution trace, architecture
flow, metric definitions, scorecards, one approved example, one rejected
example, and links to sanitized report identifiers. The page consumes only
reviewed, versioned scorecard and provenance artifacts. Opening it must never
run tests, wake Databricks, download a model, submit an LLM judge request, or
expose hidden prompts, secrets, private paths, raw filing text, or internal
stack traces.

Implementation and validation follow root `AGENTS.md`.

## Evaluation

Create a versioned golden set of at least 100 questions with expected intent,
resolved entities, policy outcome, semantic plan, result assertions, numerical
tolerances, and allowed chart schemas. Report by operation and ambiguity class:

- intent parsing;
- entity resolution;
- execution accuracy;
- numerical accuracy;
- unsupported-query rejection;
- chart correctness.

CI must run deterministic layers without live credentials. A separately gated
integration job may use a test warehouse and read-only service principal.
Offline CI can prove canonical intent-to-SQL-to-result behavior. LLM intent
quality requires recorded provider responses or a separately gated evaluation
job with an explicit budget.

### Reuse from RAG Workbench

The original RAG Workbench contains two evaluation generations. Do not port
the stale CSV/API runner (`evals/run_eval.py`) or its direct RAGAS wrapper
(`evals/ragas_eval.py`): they target an obsolete chat route and mix live
endpoint execution with scoring.

Reuse the newer `evals/rag_eval` design after its branch completes the normal
review gates:

- typed, versioned JSONL golden items and corpus records;
- exact source `chunk_id`, accession, section, ticker, and `as_of` provenance;
- a hard point-in-time gate where any future evidence fails the run;
- retrieval ablations for BM25, dense, hybrid RRF, and hybrid reranking, with
  ticker filtering on and off;
- Recall@1/5/10, MRR@10, nDCG@10, abstention and adversarial-trap scoring;
- deterministic bootstrap confidence intervals;
- tiny network-free smoke fixtures for CI and ignored full corpora/embeddings;
- machine-readable JSON plus human-readable Markdown reports;
- generation scoring disabled by default and paid calls explicitly gated.

The RAG suite and natural-language analytics suite validate different claims
and publish separate scorecards:

| Suite | What it validates | Headline gates |
|---|---|---|
| SEC RAG | evidence retrieval and grounded Q&A | zero PIT leakage, retrieval metrics, abstention, citation provenance |
| NL analytics | intent-to-deterministic-query behavior | intent/entity accuracy, policy outcome, SQL/result accuracy, numerical tolerance, chart validity |

Share report envelopes, provenance fields, bootstrap utilities, CLI
conventions, and scorecard rendering. Do not use RAG retrieval metrics as
evidence that the semantic SQL compiler is correct.

### Public evaluation surface

Evaluation runs offline in CI or a separately authorized job. Visitor requests
never execute an evaluation, download a model, call a paid judge, or access the
full corpus. A release step publishes a small reviewed scorecard artifact with:

- suite/schema version, commit SHA, golden-set version, and run timestamp;
- configuration and metric definitions;
- aggregate metrics with confidence intervals and category breakdowns;
- PIT-leak count and hard-gate status;
- passed, failed, and unsupported counts plus sanitized representative cases;
- limitations, model identity where applicable, and whether generation
  scoring was disabled;
- artifact checksum and source report identifier.

The frontend adds an **Evaluation** page and a compact scorecard on the
architecture page. It may show reviewed questions with expected intent,
retrieved source IDs, output, and failure reason. It must not expose full
filing text, hidden prompts, credentials, private paths, or raw model traces.

The backend serves only validated scorecard artifacts through a bounded GET
endpoint, or the Static Site serves them directly. Unknown fields, malformed
versions, oversized files, nonzero PIT leakage marked as success, or missing
provenance fail closed. Cache by checksum; never recompute scores at request
time.

## Implementation lanes after the integration base exists

Each lane receives a dedicated worktree and non-overlapping ownership.

### NL0 — live-NL security boundary

Owned by the Render-security lane after lane B merges. Add a distinct
`PUBLIC_NL=1` mode rather than weakening `PUBLIC_DEMO=1`. It owns:

- an exact allowlist for Databricks OAuth, the selected LLM provider,
  Turnstile, and the selected OpenTelemetry exporter variables;
- exactly one bounded POST/SSE analytics endpoint;
- body and token limits plus Turnstile verification;
- exact-origin CORS for the Render Static Site;
- CSP `connect-src` for only the API and chosen telemetry destinations;
- per-route limits implemented with lane B's existing limiter.

The selected LLM provider and OpenTelemetry backend must be named before this
lane is specified so their credential names can be allowlisted precisely.

### NL-R — Render hosting split

Deliberately replace the approved single-service Blueprint with one Render
Static Site and one Starter FastAPI service. This lane owns only hosting/build
configuration and deployment documentation. It must test the SPA rewrite,
exact frontend origin, Turnstile hostname configuration, `$PORT`, SSE heartbeat
and proxy buffering behavior, and secret-free frontend bundles. Keeping the
single same-origin service is the fallback if this split adds unacceptable
cross-origin complexity.

### NL1 — contracts and semantic registry

Owns new intent, entity, metric, operation, policy, chart, and provenance models
plus registry fixtures and pure unit tests. No API routes or Databricks client.

### NL2 — deterministic compiler and policy engine

Owns compiler, parameter binding, cost classification, output schemas, and
adversarial/mutation tests. Depends on NL1. No LLM or HTTP implementation.

### NL3 — Statement API and telemetry adapters

Owns OAuth M2M configuration, submit/poll/cancel, query tags, result limits,
Query History backfill, and mocked contract tests. Depends on NL1/NL2. No PAT,
connection pool, or live credential in CI.

### NL4 — typed orchestration and SSE

Owns the two constrained LLM adapters, typed async pipeline, OpenTelemetry,
cache/single-flight, semaphore, and SSE endpoint. It consumes NL0's Turnstile,
CORS, request-bound, and existing rate-limiter interfaces rather than defining
a second security stack.
Depends on NL1–NL3 and must preserve Render lane B's public-security boundary.

### NL5 — analytics frontend

Owns the new question, trace, provenance, chart, suggested-question, adversarial
rejection, and rationale views. It consumes checked-in API contracts/mocks until
NL4 lands. It must not edit Render configuration or backend security files.

### NL6 — golden evaluation and release validation

Owns golden fixtures, scoring/report generation, end-to-end contract tests,
load-test harness, threat cases, accessibility checks, and public scorecard.
Its load test must run before NL4's production semaphore value is finalized.
It may extract generic reporting utilities from the approved RAG harness, but
must use a separate package/data path because active RAG-evaluation branches
own `evals/` and the analytics metrics are semantically different.

## Merge and release gates

1. Refresh the repository dependency graph and create a clean integration base.
2. Complete the reviewed snapshot fallback if it remains a launch requirement.
3. Specify and implement NL0 and NL-R against that integration base.
4. Merge NL1, then NL2, then NL3; merge NL4 only after their contracts settle.
5. Develop NL5 against mocks in parallel after NL1 freezes the wire schemas.
6. NL6 and a security review gate the public deployment.
7. Validate the current Render Blueprint schema and pricing immediately before
   launch; the desired target is a React static site plus one Starter web
   service, so the existing single-service Blueprint must be deliberately
   revised in its own reviewed lane rather than edited opportunistically.

Do not publish a URL until route enumeration, secret scanning, adversarial
rejection, timeout/cancellation, cache isolation, numerical correctness, mobile
UI, and rollback tests pass. Deployment itself is an explicit owner-approved
step separate from merging code.

Shared-workspace prerequisites are explicit blockers: an administrator must
create/grant the service principal, and the owner may not control warehouse
sizing, max clusters, or auto-stop in `bootcamp_students`. Verify the live row
count before publishing the `200M+` claim and identify dedicated serving views
for every v1 metric.

## V1.1 only

Defer replay, immutable showcase snapshots, published load-test results,
production-evolution diagrams, additional metrics/operations/charts,
distributed state, and any multi-agent runtime architecture.
