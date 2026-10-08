# BUILD: transactional Lakebase outbox and Delta analytics

## 0. Assignment and base

MiMo implements this round end to end. Base it on the final approved
`slice/app-frontend-deploy` branch plus any already-merged prerequisite work.
Do not start Lakebase during the build. Do not implement native logical
replication, Lakeflow Connect, or synced tables.

This round owns migration `004`, the analytics consumer/job, the analytics API
reader/contract, and focused tests. Preserve the app lane's bounded connections,
circuit breaker, diagnostic stages, and SQL-warehouse fallback.

## 1. Numbered changes

1. **Transactional source outbox -- `db/migrations/004_analytics_outbox.sql:1`
   (new file), `db/migrations/CDC.md:1`.**
   - Create `analytics_outbox` with a monotonic `event_id` primary key,
     allowlisted `source_table`, `source_pk`, `operation` (`insert`, `update`,
     `delete`, `snapshot`), explicit `before_payload`/`after_payload` JSONB,
     `occurred_at`, optional unique `dedupe_key`, `delivered_at`, `attempt_count`,
     and bounded `last_error`. Add an index beginning with `delivered_at` and
     then `event_id`.
   - Add `SECURITY DEFINER` trigger functions with a fixed safe `search_path`,
     owner-only mutation, and revoked public execution. Attach `AFTER` row
     triggers to `watchlists`, `signals`, `orders`, `executions`, `positions`,
     `agent_actions`, `research_notes`, and `approvals`.
   - Build payloads from explicit field lists per table. Never use `to_jsonb(NEW)`
     or `SELECT *`. Exclude research-note text, agent input/output summaries,
     display names, credentials, and all future columns by default.
   - Seed one idempotent `snapshot` event for each existing source row using a
     stable non-null `dedupe_key`; reapplying the migration must not duplicate
     snapshots or triggers.
   - The source write and outbox insert must share the same Postgres transaction.
     Application roles receive no direct read/update access to outbox rows.
   - Replace `CDC.md`'s obsolete "next slice logical publication" claim with the
     chosen outbox contract, failure model, security boundary, and future native
     Lakebase-CDF migration note.

2. **Pure event semantics and Spark runner --
   `pipelines/lakebase_analytics.py:1` (new file).**
   - Keep imports offline-safe: importing the module must not require Spark,
     Databricks credentials, or Lakebase. Put normalization and aggregation into
     pure functions tested with dictionaries; acquire Spark/DB only in `main()`.
   - Claim a bounded batch of every committed row with `delivered_at IS NULL`,
     ordered for determinism. Never select completeness with only
     `event_id > last_watermark`; committed IDs can contain gaps.
   - MERGE each raw event into `lakebase_change_events` by `event_id`. After a
     successful Delta commit, mark exactly those event IDs delivered. If that
     acknowledgement fails, the next run must replay safely. Record failures in
     bounded/redacted form and leave the event pending.
   - Store an `analytics_cdc_state` row containing last successful run, maximum
     delivered event ID, pending count, source/target lag, and status. Treat the
     event-ID high water as observability only.
   - Recompute only affected UTC dates from the immutable raw events, handling
     inserts, updates (before and after), deletes, and snapshots. Event-time/PIT
     filters must use `occurred_at`; ingestion/refreshed timestamps are never a
     substitute for when the operational change became available.
   - Create and idempotently MERGE these typed Delta tables, all configured via
     `--catalog` and `--schema`:
     - `analytics_agent_activity`: UTC date x tool/action/status counts, distinct
       users, last source event/time.
     - `analytics_watchlist_changes`: UTC date x symbol additions/removals/net,
       distinct users, last source event/time.
     - `analytics_order_funnel`: UTC date x ordered funnel stage counts and
       distinct orders, including intent, approval, submission, fill,
       cancellation, rejection, and failure transitions without double-counting
       update preimages.
     - `analytics_usage_daily`: UTC date totals for retrieval/write tool calls,
       success/failure, active users, and source lag.
   - Use fixed table/column identifiers and parameterized Postgres values. Log
     counts/IDs/latency only, never JSON payload contents.

3. **Job wiring -- `resources/jobs.yml:1` (append after the existing job
   definitions).**
   - Add `lakebase_analytics_refresh` invoking the new runner with
     `${var.catalog}` and `${var.schema}`.
   - Set `max_concurrent_runs: 1`, a bounded batch size, retries with backoff, and
     a `PAUSED` schedule by default. Do not auto-start Lakebase. Keep compute
     serverless-compatible and do not change unrelated jobs.

4. **Real analytics reads -- `db/delta_adapter.py:260` (reader helpers;
   re-resolve after the app lane), `api/routes/analytics.py:1`,
   `api/schemas.py:166` (analytics models).**
   - Add one fixed allowlist mapping API section names to the four tables. No
     request value may become a table, column, ordering, or SQL fragment.
   - Read bounded recent aggregates through the app lane's Spark-or-SQL-warehouse
     adapter. Preserve timeouts and the `read_delta` freshness mapping.
   - Extend `AnalyticsResponse` with `watchlist_changes`, `order_funnel`, and
     `usage_daily`; keep legacy response fields only if compatibility requires
     them, and never populate a mismatched legacy label with unrelated data.
   - Replace unconditional empty envelopes. Each section reports real data,
     exact source table, count, and freshness based on the table's source event
     and refresh time. Missing/empty/unavailable remain honest typed envelopes.

5. **Offline tests -- `tests/rubric/test_lakebase_analytics.py:1`,
   `tests/api/test_analytics.py:1`, `tests/rubric/test_outbox_sql.py:1` (new
   files).**
   - Pure fixtures cover snapshot, insert, update, delete, duplicate replay,
     late delivery below the observed high-water ID, UTC date boundaries, and
     every order status transition.
   - Prove two identical runs produce byte-for-byte-equivalent aggregate rows
     and no duplicate event or funnel count.
   - Parse migration SQL to reject broad `to_jsonb(NEW/OLD)`, unsafe dynamic SQL,
     missing fixed search path, missing trigger tables, direct app grants, and
     non-idempotent snapshot seed logic.
   - API tests mock the existing adapter and assert non-empty data, table source,
     stale/unavailable/empty behavior, fixed query bounds, and no Lakebase call.
   - Add a bundle test for paused schedule and single concurrency.

## 2. Tests that must fail on the current code

Before implementation, copy the new tests into a clean temporary checkout of
the pre-round base. Record failures showing all of the following:

- `pipelines.lakebase_analytics` and migration `004` are absent;
- replay/late-delivery semantics are not implemented;
- `/api/analytics` still returns unconditional empty placeholders; and
- the bundle has no Lakebase analytics job.

Do not accept "test file not found" as the only red proof. At least the API
test must execute against current production code and fail on `count == 0` /
`empty is True` after the adapter fake returns rows.

## 3. Named validation mutations

Kimi and Codex must apply each mutation in a disposable copy and show a focused test
fails:

1. **WATERMARK-SKIP:** change pending selection to `event_id > watermark`; a
   committed lower-ID pending fixture must be lost and the test must fail.
2. **APPEND-DUPLICATE:** replace raw-event MERGE with append; the replay test must
   detect duplicate `event_id` and inflated aggregates.
3. **PREIMAGE-COUNTS-AS-NEW:** count the old half of an order update as a new
   funnel stage; exact stage counts must fail.
4. **LEAK-NOTE-TEXT:** add `note_text` or `input_summary` to an outbox payload;
   the migration security test must fail.
5. **PLACEHOLDER-ROUTE:** restore `_empty_envelope` for one new section; the API
   test must fail.

## 4. Offline acceptance

Run from the repository root with Lakebase stopped and no live credentials:

```bash
python3 -m pytest -q \
  tests/rubric/test_lakebase_analytics.py \
  tests/rubric/test_outbox_sql.py \
  tests/api/test_analytics.py \
  tests/test_bundle_sync.py
python3 -m pytest -q tests/api --ignore=tests/api/test_health_diagnostics.py
databricks bundle validate --target dev \
  --var 'catalog=test_catalog,schema=test_schema,lakebase_instance=test_instance,warehouse_id=test_warehouse,agent_model_endpoint=test_endpoint'
```

If the final bundle CLI uses environment-form variables instead, document the
equivalent exact command. No test may connect to Lakebase, a warehouse, or the
internet. Static imports must remain pyspark-free in the app process.

## 5. Exact owner-authorized live checks

These are deferred until owner approval to start Lakebase:

1. Record initial instance state. Ask the owner, then start
   `evangoh-capstone-lakebase`; record start time. Do not let a script start it.
2. Apply migrations and prove `004_analytics_outbox` is recorded once. Reapply
   and prove zero migrations and unchanged snapshot/outbox counts.
3. As a dedicated test principal, perform one watchlist insert/delete-equivalent
   change, one note insert/update if supported, and one order status transition.
   Capture only generated IDs, not note/prompt text.
4. Run `lakebase_analytics_refresh` once. Query the four fully qualified
   analytics tables for row counts, max source event ID/time, and duplicate
   natural keys; all duplicate queries must return zero.
5. Run the job again with no new source writes. Counts and aggregates must be
   unchanged, pending outbox count must be zero, and state must report success.
6. Insert one more event, run once, and prove exactly the expected affected-day
   metrics change while prior dates remain unchanged.
7. From the app URL, `GET /api/analytics` with real auth must return HTTP 200,
   at least the seeded sections non-empty, exact `analytics_*` sources, and no
   503/placeholder detail.
8. Record final pending count, job run URL/ID, table counts, and whether the
   owner wants Lakebase/app compute stopped immediately. Stop by default.

## 6. Handoff

Use LF line endings. Do not touch `.agents/dispatch.sh`, RAG ingestion files,
strategy files, or frontend evidence screens. Commit the round. Write
`.agentlogs/VERDICT-rubric-analytics-cdc.md` with commits, files, red proof,
all five mutation proofs, exact offline outputs, live checks marked pending,
scope exclusions, and a `SUCCESS`/`FAILURE` self-report. Kimi's independent,
commit-bound verdict and Codex final validation are still required.
