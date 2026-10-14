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

The Databricks job `lakebase_analytics_refresh` runs at 02:15 UTC daily
(`0 15 2 * * ?`). It is **UNPAUSED** by default with:

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

Each successful run writes a row to `analytics_cdc_state` with:

| Column | Description |
|---|---|
| `run_id` | ISO timestamp of the run |
| `completed_at` | ISO timestamp when run completed |
| `max_event_id` | Highest event_id in the batch |
| `pending_count` | Events remaining (0 on success) |
| `source_target_lag_s` | Seconds between last event and run completion |
| `status` | `success`, `error`, or `idle` |

Query the latest state:

```sql
SELECT * FROM {catalog}.{schema}.analytics_cdc_state
ORDER BY completed_at DESC LIMIT 5;
```

## Idempotency

- **Delta MERGE**: `merge_events_to_delta` MERGEs on `event_id` — duplicate
  delivery creates no duplicate rows.
- **Analytics recompute**: affected dates are deleted then re-inserted from
  the merged Delta table. Double-count from replay is impossible.
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

### Full catch-up

```bash
python -m pipelines.lakebase_analytics \
  --catalog {catalog} --schema {schema} --batch-size 5000 --max-batches 20
```

### Re-process specific dates

Events are re-computed per affected UTC date. To force a recompute of a
specific date, you would need to temporarily re-insert events into the outbox
(advanced — requires DBA access).

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

```sql
SELECT COUNT(*) AS pending
FROM analytics_outbox
WHERE delivered_at IS NULL;
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `LAKEBASE_URL not set` (old behavior) | Running old code | Upgrade to current version |
| `Lakebase credential mint failed` (also `Lakebase credential mint failed via SDK`, `Lakebase credential mint timed out` — from `db/lakebase.py`) | Token mint failed: SDK/CLI/permissions, or `databricks-sdk < 0.56.0` | Check Databricks auth / CLI / instance permissions; raise the `databricks-sdk` floor to `>= 0.56.0` |
| `Lakebase connection failed` (from `pipelines/lakebase_analytics.py` — the connect step, after the token mint succeeded) | Connect step failed: network / host / role / SSL | Check network reachability, `LAKEBASE_HOST`, database role, and SSL mode |
| High `source_target_lag_s` | Batch size too small or job paused | Increase `--max-batches` |
| `idle` state, no events | Outbox empty | Normal if no writes occurred |
| `another runner holds the lock` | A second runner (scheduled or manual) is active | Normal: the second run exits 0 and the active runner processes the events |
| Repeated retries | Transient DB/Delta failure | Check job logs in Databricks |