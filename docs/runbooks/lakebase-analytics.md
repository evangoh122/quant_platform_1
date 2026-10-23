# Lakebase Analytics Pipeline Runbook

## Overview

`pipelines/lakebase_analytics.py` consumes the transactional outbox from
Lakebase (Postgres), MERGEs raw events into a staging Delta table
(`lakebase_change_events`), then idempotently computes four analytics tables:

- `analytics_agent_activity` — UTC date × tool/action/status counts
- `analytics_watchlist_changes` — UTC date × symbol add/remove/net
- `analytics_order_funnel` — UTC date × funnel stage counts
- `analytics_usage_daily` — UTC date × retrieval/write tool totals

## Schedule

The Databricks job `lakebase_analytics_refresh` is defined at 02:15 UTC daily
(`0 15 2 * * ?`, `timezone_id: UTC`). It is **PAUSED by default** (owner
decision 2026-10-23: *"Keep it paused but give me the option to schedule"*):
a deploy ships the job with its schedule paused, so nothing runs nightly until
the owner opts in. The schedule is otherwise unchanged:

- `max_concurrent_runs: 1` — only one run at a time
- `max_retries: 2` — up to 2 automatic retries on failure (on the
  `refresh_analytics` task; task-level field in the bundle schema)
- `min_retry_interval_millis: 60000` — 60-second minimum between retries
  (on the `refresh_analytics` task)
- `timeout_seconds: 3600` — 1-hour timeout on the `refresh_analytics` task.
  There is **no** job-level `timeout_seconds`: a per-run timeout equal to one
  task attempt would let the first timed-out attempt consume the whole run
  budget and starve the retries. The run budget is therefore uncapped (a stuck
  run is capped per attempt by the task timeout).
- **No `email_notifications`** — see [Failure notifications](#failure-notifications).

### Pausing and unpausing

`resources/jobs.yml` binds `schedule.pause_status` to the bundle variable
`analytics_schedule_pause_status`, declared in `databricks.yml` with the
description "PAUSED (default) or UNPAUSED for the nightly
lakebase_analytics_refresh schedule" and the default `PAUSED`. Every committed
target keeps that default (`tests/test_bundle_sync.py` guards it, including the
accepted values `PAUSED` / `UNPAUSED`).

Run the job **once, on demand**, without touching the schedule:

```bash
databricks bundle run lakebase_analytics_refresh -t dev      # or -t prod
```

**Enable the nightly schedule** with any one of:

1. Deploy with the variable set — no committed change needed:

   ```bash
   databricks bundle deploy -t dev --var analytics_schedule_pause_status=UNPAUSED
   ```

   Repeat the `--var` on every later deploy that should keep it enabled: a
   plain `databricks bundle deploy` restores the committed default `PAUSED`.

2. Set `analytics_schedule_pause_status: UNPAUSED` in the `variables:` block of
   a target in `databricks.yml`. This is a committed change to the default, so
   `tests/test_bundle_sync.py` must be updated in the same commit — that guard
   is what keeps every target `PAUSED` unless the owner changes it deliberately.

3. Resume the schedule in the Databricks Jobs UI for
   `quant-platform-lakebase-analytics-<target>`. No repository change, but the
   next bundle deploy re-applies `PAUSED` and pauses it again.

**Pause again** by deploying with `--var analytics_schedule_pause_status=PAUSED`
(or plain `databricks bundle deploy`, which restores the default), or with
"Pause" on the job schedule in the Databricks Jobs UI.

## Failure notifications

The job intentionally ships **without** an `email_notifications` block and the
bundle declares **no** `alert_email` variable: `${var.alert_email}` resolved to
`""` in dev and prod, and the Jobs API may reject an empty notification
address and fail the whole bundle deploy.

To add failure notifications **without committing an address**, an operator
picks one of:

1. **Target override at deploy time** — add the block with a real address in a
   local override that is deployed but never committed (e.g. temporarily under
   `targets.<target>.resources.jobs.lakebase_analytics_refresh` in a local
   `databricks.yml`, or a local `resources/*.yml` override), then deploy:

   ```yaml
   resources:
     jobs:
       lakebase_analytics_refresh:
         email_notifications:
           on_failure:
             - "you@example.com"
   ```

   Revert the local edit after deploy; the committed bundle stays
   address-free. Never commit a personal address.

2. **Run history / workspace alerts** — no bundle change at all: watch the
   job's run history in the Databricks UI, or configure a workspace alert /
   notification destination outside this repository for `lakebase_analytics`
   failures.

Note that a bundle-managed job's settings are restored on the next
`databricks bundle deploy`, so route 1 must be repeated (or route 2 used) after
any redeploy.

## Connection source

The pipeline acquires a Postgres connection in this priority:

1. **`LAKEBASE_URL` env var** — local-dev override, logged as `url-override`
   (value is never logged). Set only for local testing.
2. **Minted OAuth token** — short-lived token from `db.lakebase` credential
   minting (Databricks CLI or SDK). Logged as `minted-oauth`.

Tokens are never written to logs, exceptions, or `analytics_cdc_state`.
Failures from the token provider or the driver are re-raised as sanitized
errors (`raise ... from None`): the message carries only the exception type
name — never a URL, password or token — and no credential text remains
reachable through `__cause__`/`__context__`.

## Single-runner lock

The runner enforces a real single-runner lock across **both** entry points
(the scheduled job and manual CLI runs — `max_concurrent_runs: 1` covers only
scheduled runs):

- On startup, `main()` takes a Postgres **SESSION-level** advisory lock with
  `SELECT pg_try_advisory_lock(...)` using the module constant
  `RUNNER_LOCK_KEY` (a fixed 64-bit key derived from the string
  `lakebase_analytics`), on the same **DIRECT (non-pooled)** connection the
  pipeline uses (`open_lakebase_connection`; never on a `psycopg_pool` pooled
  connection — a pooled connection would not hold the session lock).
- If the lock is **not** acquired, the run logs `another runner holds the
  lock; exiting without claiming events` and **exits 0 cleanly** without
  claiming any outbox events and without marking anything failed. This is not
  an error: the other runner processes the events.
- On every exit path the lock is released with `pg_advisory_unlock` in a
  `finally` (it is also released when the connection closes).

Why the lock is needed: `claim_batch` keeps `FOR UPDATE SKIP LOCKED` row locks
only until commit, while `delivered_at` stays NULL until the whole pipeline
succeeds — without the advisory lock a second runner could claim the same
events and two delete+insert recomputes of the same dates could overwrite each
other (a stale snapshot winning, both marking delivered).

## How to check `analytics_cdc_state`

`analytics_cdc_state` is **best-effort and status-specific**: a convenience
log of runs, not a delivery ledger. The authoritative delivery record is
`analytics_outbox.delivered_at` in Lakebase. Each written row carries:

| Column | Description |
|---|---|
| `run_id` | ISO timestamp of the run |
| `completed_at` | ISO timestamp when the row was written |
| `max_event_id` | `success`: highest `event_id` in the delivered batch. `error` and `idle`: `0` (not populated on those paths) |
| `pending_count` | `success` and `idle`: `0`. `error`: number of events claimed by the failed batch — they stay re-claimable |
| `source_target_lag_s` | `success`: seconds between the last claimed event's `occurred_at` and run completion. `error` and `idle`: `0.0` |
| `status` | `success`, `error`, or `idle` |

Values per status come from `run_pipeline`:

- `success` — written **after** `mark_delivered` has committed and outside
  the delivery-failure handler (see [Idempotency](#idempotency)).
- `error` — written when the pipeline raises before `mark_delivered`; the
  events were re-marked failed (`delivered_at` stays NULL) and remain
  re-claimable.
- `idle` — the run claimed 0 events.

**A successful batch can have no state row at all.** The `success` write is
best-effort: if it fails after delivery, the run logs `record_state failed
after delivery (...)` and stays successful without writing any row. A missing
row is therefore not evidence of failure — check the run logs and
`analytics_outbox.delivered_at` instead.

Query the latest state:

```sql
SELECT * FROM {catalog}.{schema}.analytics_cdc_state
ORDER BY completed_at DESC LIMIT 5;
```

## Idempotency

- **Delta MERGE**: `merge_events_to_delta` MERGEs on `event_id` — duplicate
  delivery creates no duplicate rows.
- **Analytics recompute**: affected dates are deleted then re-inserted from
  the merged Delta table. This makes duplicate *delivery* of the same
  `event_id` double-count-free (the Delta MERGE is keyed on `event_id` and
  every recompute restarts from the merged table). It does **not** make a
  plain re-insert safe: `analytics_outbox.event_id` is generated
  (`BIGINT GENERATED ALWAYS AS IDENTITY`), so re-inserting already-processed
  events mints new ids, the Delta MERGE treats them as new rows, and the date
  recompute counts the logical event twice. Replay must re-queue the
  ORIGINAL rows — see [Re-process specific dates](#re-process-specific-dates).
- **Delivery confirmation**: events are marked `delivered_at` ONLY after the
  full pipeline (Delta MERGE + analytics recompute) succeeds. A crash before
  confirmation leaves events re-claimable.
- **State write after delivery**: the success row in `analytics_cdc_state` is
  written after `mark_delivered` has committed and **outside** the
  delivery-failure handler. If that state write fails, the run logs a warning
  naming only the exception class (e.g. `record_state failed after delivery
  (RuntimeError); events stay delivered`) and **does not fail the run** and
  **never calls `mark_failed`** — delivered events must not be reverted and no
  misleading error is recorded for them. Failures *before* `mark_delivered`
  still call `mark_failed` and leave the events re-claimable.

## How to replay

### Manual single-batch run

```bash
python -m pipelines.lakebase_analytics \
  --catalog {catalog} --schema {schema} --batch-size 100 --max-batches 1
```

### Bounded catch-up

`run_batches` stops after `--max-batches` even when more work remains, so
this command can leave pending events after 20 batches — it is **not** a
full catch-up:

```bash
python -m pipelines.lakebase_analytics \
  --catalog {catalog} --schema {schema} --batch-size 5000 --max-batches 20
```

Rerun it (or raise `--max-batches`) until a run reports `claimed 0 events`
(the `idle` state row): only then is the backlog drained.

### Re-process specific dates

Events are re-computed per affected UTC date. `analytics_outbox.event_id` is
generated at insert time (`BIGINT GENERATED ALWAYS AS IDENTITY`), so the
**only** supported replay re-queues the ORIGINAL rows and preserves their
`event_id`. The pipeline re-claims any row whose `delivered_at` is NULL —
exactly the reset `mark_failed` performs on a failed batch — so no new code
path is involved:

1. Identify the original rows in Lakebase (Postgres — see
   [Pending outbox events](#pending-outbox-events) for the connection and
   schema), e.g. by `event_id` range or by `occurred_at` date and
   `source_pk`.
2. Reset delivery status on exactly those rows (requires DBA/write access to
   `analytics_outbox`):

   ```sql
   UPDATE analytics_outbox
   SET delivered_at = NULL, last_error = NULL
   WHERE event_id BETWEEN {first_event_id} AND {last_event_id};
   ```

3. Rerun the pipeline (manual single-batch or bounded catch-up above). The
   rows are re-claimed in `event_id` order, MERGEd on their original
   `event_id` (no new Delta rows), and the affected UTC dates are deleted
   and recomputed from `lakebase_change_events`.

**Never re-insert events to force a recompute.** A plain insert assigns a NEW
generated `event_id`, the Delta MERGE treats the row as a new event, and the
date recompute double-counts the logical event. There is no CLI flag or
function that re-queues a date range automatically (this runbook previously
suggested re-inserting rows; that path double-counts and is not supported).
If the original rows have been deleted from `analytics_outbox`, no supported
replay remains for their dates.

## Verification queries

### Row counts per analytics table

```sql
SELECT 'agent_activity' AS tbl, COUNT(*) FROM {catalog}.{schema}.analytics_agent_activity
UNION ALL
SELECT 'watchlist_changes', COUNT(*) FROM {catalog}.{schema}.analytics_watchlist_changes
UNION ALL
SELECT 'order_funnel', COUNT(*) FROM {catalog}.{schema}.analytics_order_funnel
UNION ALL
SELECT 'usage_daily', COUNT(*) FROM {catalog}.{schema}.analytics_usage_daily;
```

### State table tail

```sql
SELECT run_id, status, max_event_id, pending_count, source_target_lag_s
FROM {catalog}.{schema}.analytics_cdc_state
ORDER BY completed_at DESC LIMIT 10;
```

### Event by `source_pk` (note id)

```sql
SELECT event_id, source_table, source_pk, operation, occurred_at
FROM {catalog}.{schema}.lakebase_change_events
WHERE source_pk = '{your_source_pk}'
ORDER BY event_id;
```

### Pending outbox events

`analytics_outbox` is a **Lakebase (Postgres)** table, not a Databricks
catalog table: run this query on the Lakebase database (psql or a psycopg
connection like `db/lakebase.py`'s), **not** in Databricks SQL. The table is
created in the `public` schema (`db/migrations/004_analytics_outbox.sql`);
connect with a `search_path` that includes `public` (the app's connections
set `search_path` to `LAKEBASE_SCHEMA`, default `public` — `db/lakebase.py`)
or qualify the table as `public.analytics_outbox`. The role needs `SELECT` on
the table: its ACL revokes all privileges from `PUBLIC`, so use the table
owner or a role explicitly granted `SELECT`.

```sql
SELECT COUNT(*) AS pending
FROM public.analytics_outbox
WHERE delivered_at IS NULL;
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `LAKEBASE_URL not set` (old behavior) | Running old code | Upgrade to current version |
| `Lakebase credential mint failed` (also `Lakebase credential mint failed via SDK`, `Lakebase credential mint timed out` — from `db/lakebase.py`) | Token mint failed: SDK/CLI/permissions, or `databricks-sdk` below `0.57.0` (0.56.0 mints but its `DatabaseCredential` lacks `expiration_time`) | Check Databricks auth / CLI / instance permissions; raise the `databricks-sdk` floor to `>= 0.57.0` |
| `Lakebase connection failed` (from `pipelines/lakebase_analytics.py` — the connect step, after the token mint succeeded) | Connect step failed: network / host / role / SSL | Check network reachability, `LAKEBASE_HOST`, database role, and SSL mode |
| High `source_target_lag_s`, schedule paused or never enabled | No runs happen while the job schedule is PAUSED, so `--max-batches` has no effect | Run on demand (`databricks bundle run lakebase_analytics_refresh`) or enable the schedule ([Pausing and unpausing](#pausing-and-unpausing)) |
| High `source_target_lag_s`, `--batch-size` too small | Each batch claims too few events for the event rate | Increase `--batch-size` |
| High `source_target_lag_s`, backlog larger than one run's allowance | A single run processes at most `--max-batches` × `--batch-size` events | Increase `--max-batches` (work allowed in one run) and/or rerun until a run claims 0 events |
| `idle` state, no events | Outbox empty | Normal if no writes occurred |
| `another runner holds the lock` | A second runner (scheduled or manual) is active | Normal: the second run exits 0 and the active runner processes the events |
| Repeated retries | Transient DB/Delta failure | Check job logs in Databricks |