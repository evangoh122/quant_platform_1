# Real Analytics metrics plan

## Decision and current-state diagnosis

Build the three missing datasets from observed records and repair the Agent Activity wire contract. Do not seed, backfill, or display synthetic values. A section with no eligible input remains empty and states why; a failed or absent table is unavailable, not empty; a late source is stale. The scheduled job remains `PAUSED` until the owner approves activation.

The current endpoint names all three absent tables in `api/routes/analytics.py:20-28` and reads them at `api/routes/analytics.py:76-79`; the adapter merely allow-lists those names at `db/delta_adapter.py:484-492`. No transform creates them. Worse, `db/delta_adapter.py:504-518` catches both Spark and warehouse failures and returns `[]`, so `api/deps.py:386-394` cannot distinguish “table does not exist” from a valid zero-row result. That must be corrected as part of the typed empty/error contract.

### Root cause of Agent Activity `—`

The four real rows are not shaped like the UI's generic metric rows:

- `pipelines/lakebase_analytics.py:150-198` emits `event_date`, `tool_name`, `action_type`, `status`, `call_count`, `distinct_users`, `last_source_event_id`, and `last_source_time`.
- `_build_envelope` passes those dictionaries through unchanged at `api/routes/analytics.py:38-54`, but `AnalyticsResponse.agent_activity` is declared as `Envelope[AnalyticsItem]` at `api/schemas.py:217-227`. `AnalyticsItem` only declares `metric`, `value`, and `detail`, with empty/null defaults; Pydantic therefore drops the activity fields and serializes each row as an empty metric with `value=null`.
- The mirrored frontend contract repeats the wrong shape at `frontend/src/api/types.ts:159-169`. `frontend/src/screens/SystemHealth.tsx:18-22` keys and labels on `item.metric`/`item.detail` and renders `item.value ?? '—'`, so every valid aggregate becomes `—` (and also has an unsafe duplicate empty key).

Fix this with section-specific API models and renderers, not by flattening every dataset into lossy `metric/value/detail` triples. Preserve the existing activity fields and present a stable row label such as `tool_name · action_type · status`, with `call_count`, `distinct_users`, and date shown explicitly.

## Exact data contracts

All timestamps are UTC. Decimal metrics remain numeric in Delta and JSON. Every output carries `computed_at`, source maxima, and a machine-readable `empty_reason`/`error_code` in its envelope when no rows can be returned.

### `analytics_latency`

There is not enough durable data to calculate this table today. `agent/runtime.py:65-76` has `AuditEntry.latency_ms`, and runtime emits it (for example `agent/runtime.py:403-407`), but the default sink is a no-op at `agent/runtime.py:84-88`. The durable `agent_actions` schema has only one `created_at` timestamp and no duration/start/end at `db/migrations/001_operational_schema.sql:116-129`; migration 005 adds trace/decision metadata but no timing at `db/migrations/005_agent_runtime.sql:25-40`. The outbox payload also omits timing at `db/migrations/004_analytics_outbox.sql:433-487`. A single timestamp cannot yield latency.

First add `latency_ms DOUBLE PRECISION` (non-negative check, nullable for historical rows) and preferably `started_at TIMESTAMPTZ`/`completed_at TIMESTAMPTZ` to `agent_actions`. Persist one row for every runtime tool attempt, including failures, from the audit sink; include the new fields plus `trace_id` and `step` in the outbox payload. Measure the tool execution wall time around `ToolRegistry.execute`, not model-response latency: the existing `response.latency_ms` is model-call time and must not be mislabeled as tool latency. Historical rows stay null and are excluded.

Then create one row per `(event_date, tool_name)`:

| Column | Definition |
|---|---|
| `event_date` | UTC date of `completed_at` |
| `tool_name` | persisted real tool name |
| `p50_latency_ms` | `percentile_approx(latency_ms, 0.50)` over non-null, finite, non-negative attempts |
| `p95_latency_ms` | `percentile_approx(latency_ms, 0.95)` over the same population |
| `call_count` | count of timed attempts |
| `error_count` | count whose persisted result status is not success |
| `last_source_event_id` | maximum contributing outbox event ID |
| `last_source_time` | maximum contributing completion/occurrence time |
| `computed_at` | pipeline computation timestamp |

If no timed actions exist, return empty with `empty_reason="latency_not_recorded"`; never turn legacy nulls into zero milliseconds.

### `analytics_stream_freshness`

This is a current snapshot with one row per configured source, not a made-up aggregate. Each source registry entry must name its real table, real event column, real ingest/processed column, expected cadence, and calendar policy. Only register a source after schema introspection confirms both timestamps. Initial sources are:

| `source_name` | Event maximum | Ingest maximum | Expected cadence / stale rule |
|---|---|---|---|
| `lakebase_change_events` | `max(occurred_at)` | `max(ingested_at)` (both defined by `pipelines/lakebase_analytics.py:90-99` and populated at `pipelines/lakebase_analytics.py:450-465`) | daily job cadence; stale when `now - max_ingest_ts > 26h`, while the configured job is `PAUSED` this is honestly reported as stale/paused rather than fresh |
| `gold_trading_signals` | `max(prediction_ts)` | `max(processed_ts)` (contract at `ml/score.py:21-33`) | one publication per completed US trading session; stale after the next expected XNYS-session publication deadline, not on weekends/holidays |
| market Bronze sources with verified lineage | their actual `event_ts` | their actual `ingest_ts` | source-specific scheduled cadence; daily sources use the next expected XNYS publication deadline, intraday sources use their configured interval plus grace |

Do not invent a common timestamp column or silently omit configured sources. A row contains `source_name`, `source_table`, `max_event_ts`, `max_ingest_ts`, `observed_at`, `event_lag_seconds = observed_at - max_event_ts`, `ingest_lag_seconds = observed_at - max_ingest_ts`, `expected_cadence_seconds`, `stale_after_ts`, `is_stale`, and `reason`. An existing empty source has null maxima, `is_stale=true`, `reason="source_empty"`; missing timestamp columns or a read failure produce an unavailable/error row and make the section unavailable. Because ingest time can be current while provider events are old, the UI shows both lags.

Overwrite this small snapshot atomically on a successful complete scan (or `MERGE` by `source_name` plus delete registry entries no longer present). Never leave yesterday's apparently healthy rows after a partial failure.

### `analytics_model_performance`

Evaluate only realised `gold_trading_signals` rows, grouped by `(model_version, horizon)`. The signal contract is `signal_id`, `symbol`, `prediction_ts`, `horizon`, `direction`, `probability`, `model_version`, `feature_snapshot_id`, `status`, `processed_ts` at `ml/score.py:21-33`. For the current `1d` horizon, reproduce the repository's label semantics exactly: for each signal, D is the latest symbol close with `close_ts <= prediction_ts`; N is the next trading-date close; realised return is `close_N / close_D - 1`; `label = 1` iff `close_N > close_D`; and `label_ts = close_ts_N`. These semantics are already specified at `ml/baseline_labels.py:85-112` and the source close query at `scripts/publish_baseline_signals.py:50-69`.

The close source is real regular-session minute data (`silver_ohlcv`, `is_regular_session=true`, `timespan='minute'`) collapsed to the last close per symbol/trading date. Do not join a signal to an arbitrary calendar `date + 1`, and do not reuse a backward-looking `return_1d` without proving it has the same D/N and availability semantics. Add a horizon strategy registry: implement `1d` now; unsupported legacy `30m` rows remain unscored with `reason="unsupported_horizon"` until an exact 30-minute event-time labeler is implemented.

Eligibility is the non-negotiable PIT filter `label_ts IS NOT NULL AND label_ts <= evaluation_as_of`. Never score the latest/open signal merely because its prediction exists. For 1-day labels, enforce `max_gap_days=5` calendar days between trading date D and trading date N (as measured by `daily_close_labels` in `ml/baseline_labels.py:85-112`); when D-to-N exceeds five calendar days, `label`, `label_ts`, and `realised_return` remain null and the signal is excluded from realised metrics. Persist one row per `(evaluation_date, model_version, horizon)` with:

- `realised_count`: eligible signal count;
- `hit_count` and `hit_rate`: a hit is `UP` with positive realised return or `DOWN` with non-positive realised return (reject/flag unsupported direction values rather than guessing);
- `auc`: ROC AUC of `probability` against the binary realised label, null with `auc_reason="single_class"` when fewer than two classes exist;
- `first_prediction_ts`, `last_prediction_ts`, `max_label_ts`, `computed_at`, and source row counts.

An empty signal table returns `no_signals_published`; signals with no closed label return `no_realised_signals`; only unsupported horizons return `unsupported_horizon`. No count, hit rate, or AUC is fabricated. Recomputing a historical evaluation partition is expected because new labels close after signals were published.

## Spark transforms and orchestration

Extend the analytics implementation with focused transform modules if keeping all logic in `pipelines/lakebase_analytics.py` would couple Lakebase CDC to market evaluation. Keep pure row/label functions independently testable without Spark.

- Existing Lakebase aggregates continue to recompute all rows for affected UTC dates, but fix the current empty-output hole: `upsert_analytics` only writes when lists are nonempty at `pipelines/lakebase_analytics.py:539-565`, leaving stale rows when an affected date recomputes to zero. Use atomic overwrite-by-affected-partition (`replaceWhere`) or a transactionally safe delete-plus-insert that also deletes on empty output.
- Latency is derived from the same immutable `lakebase_change_events` replay and written by affected `event_date`. Use a keyed Delta `MERGE` or overwrite the complete affected partitions; replaying the same `event_id` must not change counts/percentiles.
- Model performance reads all signals whose labels may have closed through `evaluation_as_of`, then overwrites the complete `evaluation_date` partition (or `MERGE`s the full `(evaluation_date, model_version, horizon)` result and deletes keys absent from recomputation). Store `evaluation_as_of` so runs are reproducible.
- Stream freshness scans the explicit registry and atomically replaces the full snapshot only after every source has a classified result.

Wire the metric transforms as dependent tasks in `lakebase_analytics_refresh` in `resources/jobs.yml:112-131`: CDC/instrumentation-derived aggregates first, then model performance and freshness after their source tables are available. A separate metrics task is preferable to forcing market-table evaluation through the Postgres connection required by the current runner. Preserve `max_concurrent_runs: 1`, task failure propagation, and `pause_status: PAUSED` (`resources/jobs.yml:112-130`; guarded by `tests/test_bundle_sync.py:54-72`). Do not activate or manually run the job without owner approval.

## API and frontend contract

Replace the generic `AnalyticsItem` for these four sections with explicit `AgentActivityItem`, `LatencyItem`, `StreamFreshnessItem`, and `ModelPerformanceItem` models in `api/schemas.py`, mirrored exactly in `frontend/src/api/types.ts`. Add section metadata sufficient for honest states: `empty_reason`, `as_of`, and a sanitized error code/detail. Keep raw backend exception text out of responses.

Make `read_analytics_table` deterministic and bounded: explicit section-specific ordering (the current universal `ORDER BY event_date` at `db/delta_adapter.py:513-518` is invalid for a freshness snapshot), explicit projected columns, and exception propagation to `read_delta`. A missing table/read failure becomes `freshness.state="unavailable"`; zero valid rows becomes `empty`; nonempty rows are `fresh` or `stale` from their real timestamps, never automatically fresh merely because a row exists.

Use dedicated cards/tables in `frontend/src/screens/SystemHealth.tsx`:

- Agent Activity: tool/action/status, calls, users, and date. Controlling timestamp: `last_source_time` (max `occurred_at` from CDC events). Expected cadence: daily, matching the `lakebase_analytics_refresh` job schedule. Grace rule: stale when `now - max(last_source_time) > 26h` while the job is active; while PAUSED, stale is reported honestly. Deterministic stale behavior: stale rows remain visible with their timestamp and a warning banner.
- Latency: tool/date, p50, p95, calls, errors; milliseconds only when present. Controlling timestamp: `completed_at` from tool execution. Expected cadence: daily, same job as Agent Activity. Grace rule: stale when `now - max(completed_at) > 26h`. Deterministic stale behavior: stale rows remain visible; null historical latency is excluded, never coerced to zero.
- Stream Freshness: source, event time, ingest time, both lags, expected cadence, and stale status. Controlling timestamp: `max_event_ts` and `max_ingest_ts` per source. Expected cadence: source-specific (daily for Lakebase CDC, per-session for trading signals). Grace rule: Lakebase stale after 26h; trading signals stale after next expected XNYS session deadline. Deterministic stale behavior: stale rows remain visible with reason; empty sources show `is_stale=true, reason="source_empty"`.
- Model Performance: model version, horizon, realised count, hit rate, AUC (show “AUC unavailable — single realised class” rather than `—`). Controlling timestamp: `max_label_ts` (latest closed label). Expected cadence: per evaluation run, triggered after signal labels close. Grace rule: only signals with `label_ts <= evaluation_as_of` are scored; open signals are excluded. Deterministic stale behavior: stale data remains visible; recomputation is expected as new labels close.

The UI distinguishes loading, empty, stale, and unavailable. Empty copy comes from the server reason, for example “No realised 1d signals yet; open signals are not scored.” Stale data remains visible with its timestamp and warning. Unavailable shows retry/error state. Remove `frontend/src/screens/SystemHealth.tsx:15`'s claim that metrics “appear once the analytics pipeline populates it”; that sentence is false unless a pipeline exists and provides no actionable reason.

## Build slices and review gates

Each implementation slice follows the repository workflow and must use LF line endings, leave `.agents/dispatch.sh` untouched, commit, and write a verdict. Tests are added first and must be demonstrated failing on current `origin/main`. The checker repeats every named mutation and confirms the intended test fails.

### AN1 — Typed contracts and Agent Activity repair

Files: `api/schemas.py:217-230`, `api/routes/analytics.py:20-89`, `db/delta_adapter.py:482-518`, `frontend/src/api/types.ts:159-170`, `frontend/src/screens/SystemHealth.tsx:11-27`, `tests/api/test_analytics.py`, and new `frontend/src/screens/SystemHealth.test.tsx`.

Tests that fail now: a real activity row survives response validation with `tool_name`, `call_count`, and `distinct_users`; missing-table exceptions produce unavailable rather than empty; each section uses explicit ordering/projection; frontend renders `42 calls` and `3 users` and never `—`; reason-specific empty and unavailable copy; no duplicate blank React keys.

Named mutations: restore `Envelope[AnalyticsItem]`; swallow adapter exceptions; map activity via `metric/value`; replace the reason with the old “appears once” copy.

Acceptance:

```bash
pytest -q tests/api/test_analytics.py
npm --prefix frontend test -- --run frontend/src/screens/SystemHealth.test.tsx
npm --prefix frontend run build
```

### AN2 — Persist real tool timing and build latency

Files: new additive `db/migrations/006_agent_action_latency.sql`, the production audit sink/wiring in `agent/runtime.py` and the API composition root, `db/migrations/004_analytics_outbox.sql` only through a forward migration that replaces its function (do not edit applied migration 004), `pipelines/lakebase_analytics.py`, `tests/rubric/test_outbox_sql.py`, `tests/rubric/test_lakebase_analytics.py`, runtime audit tests, and API/frontend fixtures.

Tests that fail now: successful and failed tool attempts persist non-negative tool wall time; model latency cannot populate tool latency; outbox includes timing/trace/step; null legacy latency is excluded; exact p50/p95 fixtures; rerun does not double-count; recomputation to zero removes the old date partition; `latency_not_recorded` is returned when appropriate.

Named mutations: substitute `response.latency_ms`; coalesce null latency to zero; time only successful calls; drop failure rows; append instead of idempotent partition replacement; omit timing from the outbox payload.

Acceptance:

```bash
pytest -q tests/agent tests/rubric/test_outbox_sql.py tests/rubric/test_lakebase_analytics.py tests/api/test_analytics.py
```

### AN3 — PIT-safe realised model performance

Files: new focused transform such as `pipelines/analytics_model_performance.py`, shared daily-label helper only if needed, `pipelines/lakebase_analytics.py` orchestration hook, `tests/analytics/test_model_performance.py`, `tests/ml/test_baseline_labels.py`, `tests/api/test_analytics.py`, and frontend model-performance tests.

Tests that fail now: Friday-to-Monday is the next trading day; a signal before D close cannot use that future close as D; `label_ts > evaluation_as_of` is excluded; open latest signals are excluded; grouping separates model version and horizon; 1d hit rate/count/AUC exact fixture; single-class AUC is null with reason; 30m is unsupported rather than scored as 1d; rerun replaces the evaluation partition.

Named mutations: score all published signals; join on calendar date plus one; use a close after `prediction_ts` as D; remove the `label_ts <= evaluation_as_of` predicate; merge horizons; return AUC zero for one class; relabel 30m as 1d.

Acceptance:

```bash
pytest -q tests/analytics/test_model_performance.py tests/ml/test_baseline_labels.py tests/api/test_analytics.py
```

### AN4 — Source-aware stream freshness

Files: new focused transform/config such as `pipelines/analytics_stream_freshness.py`, `db/delta_adapter.py`, `api/routes/analytics.py`, `api/schemas.py`, `frontend/src/api/types.ts`, `frontend/src/screens/SystemHealth.tsx`, `tests/analytics/test_stream_freshness.py`, API/frontend tests.

Tests that fail now: independent event and ingest maxima/lags; old events with a recent ingest are still shown as old; 26-hour Lakebase threshold; XNYS weekend/holiday deadline; empty source reason; schema/read failure is unavailable; partial scan cannot publish a falsely healthy snapshot; exact stale state and timestamps render.

Named mutations: use `now()` for either source maximum; use ingest lag as event lag; apply one cadence to every source; mark empty fresh; skip failed sources; publish partial output; use calendar days for the signal SLA.

Acceptance:

```bash
pytest -q tests/analytics/test_stream_freshness.py tests/api/test_analytics.py
npm --prefix frontend test -- --run frontend/src/screens/SystemHealth.test.tsx
npm --prefix frontend run build
```

### AN5 — Paused orchestration and end-to-end honesty

Files: `resources/jobs.yml:112-131`, `tests/test_bundle_sync.py`, an end-to-end analytics contract test, and the analytics operations runbook.

Tests that fail now: dependency order includes CDC, model performance, and freshness tasks; all task failures fail the run; single concurrency remains; every target remains paused; API fixtures exercise data/empty/stale/unavailable for all four cards; bundle resolves each new Python file.

Named mutations: unpause the job; remove a dependency; allow concurrent runs; continue after a failed source scan; omit a transform from bundle sync.

Acceptance:

```bash
pytest -q tests/test_bundle_sync.py tests/api/test_analytics.py tests/analytics tests/rubric/test_lakebase_analytics.py
npm --prefix frontend test -- --run
npm --prefix frontend run build
databricks bundle validate
```

## Rollout gates

Land AN1 first so existing activity is useful and missing tables are reported honestly. Land AN2 before claiming latency exists. AN3 and AN4 may follow independently, then AN5 wires the reviewed transforms. With the job still paused, validate migrations, run each transform at an explicit `evaluation_as_of`, inspect table schemas/counts/source maxima, verify an open signal is absent from performance, and compare percentile fixtures to raw timed attempts. Owner approval is required before the first production migration/run and again before changing the recurring schedule from `PAUSED`.
