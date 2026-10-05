# Lakebase change-data capture (CDC) — outbox pattern

This document describes the **transactional outbox** pattern used for CDC.
The previous logical-republication approach is superseded.

## Architecture

```
┌─────────────┐     AFTER trigger     ┌──────────────────┐
│ source table │ ─────────────────────► │ analytics_outbox │
│ (8 tables)  │   SECURITY DEFINER     │ (event_id PK)    │
└─────────────┘                        └────────┬─────────┘
                                                │
                                   Spark/Delta runner polls
                                   (delivered_at IS NULL)
                                                │
                                        ┌───────▼────────┐
                                        │ lakebase_change │
                                        │   _events (Δ)  │
                                        └───────┬────────┘
                                                │
                                   ┌────────────┼────────────┐
                                   ▼            ▼            ▼
                          analytics_       analytics_   analytics_
                          agent_activity   order_funnel  usage_daily
```

## Outbox contract

| Column          | Type          | Description                                          |
| :-------------- | :------------ | :--------------------------------------------------- |
| `event_id`      | BIGINT IDENTITY | Monotonic primary key. Gap-free within a session but may have gaps across restarts. |
| `source_table`  | TEXT CHECK     | One of the eight allowlisted behavioural tables.     |
| `source_pk`     | TEXT           | Primary key of the source row (pipe-delimited for composite PKs). |
| `operation`     | TEXT CHECK     | `insert`, `update`, `delete`, or `snapshot`.         |
| `before_payload`| JSONB          | Row state before the change (NULL for inserts).      |
| `after_payload` | JSONB          | Row state after the change (NULL for deletes).       |
| `occurred_at`   | TIMESTAMPTZ    | Transaction timestamp (default `now()`).             |
| `dedupe_key`    | TEXT UNIQUE    | Idempotency key: `{op}:{table}:{pk}`.               |
| `delivered_at`  | TIMESTAMPTZ    | NULL = pending; set after successful Delta commit.   |
| `attempt_count` | INTEGER        | Number of delivery attempts (default 0).             |
| `last_error`    | TEXT           | Bounded/redacted last error message.                 |

Pending events are selected with `delivered_at IS NULL ORDER BY event_id LIMIT :batch_size`.

## Payload construction

Payloads are built from **explicit field lists** per source table using
`jsonb_build_object()`. The following sensitive fields are **never included**:

- `research_notes.note_text` — analyst note content
- `agent_actions.input_summary` — agent input text
- `agent_actions.output_summary` — agent output text
- `users.display_name` — PII
- Any credentials or tokens
- Any future columns by default (opt-in only)

Numeric fields are cast to TEXT to preserve precision in JSONB.

## Source tables

| Table            | Source PK               | Captured fields (excl. sensitive)                  |
| :--------------- | :---------------------- | :------------------------------------------------- |
| `watchlists`     | `watchlist_id`          | watchlist_id, user_id, symbol, created_at, source_action_id |
| `signals`        | `signal_id`             | signal_id, symbol, prediction_ts, model_version, direction, probability, feature_snapshot_id, status |
| `orders`         | `order_id`              | order_id, user_id, signal_id, symbol, broker, broker_order_id, side, quantity, notional, order_type, limit_price, status, approved_by, approved_at, submitted_at, idempotency_key, created_at |
| `executions`     | `execution_id`          | execution_id, order_id, broker_execution_id, fill_qty, fill_price, commission, executed_at |
| `positions`      | `account_id\|symbol`    | account_id, symbol, quantity, avg_cost, market_price, realized_pnl, unrealized_pnl, updated_at |
| `agent_actions`  | `action_id`             | action_id, user_id, tool_name, action_type, status, created_at |
| `research_notes` | `note_id`               | note_id, user_id, symbol, signal_id, created_at, updated_at |
| `approvals`      | `approval_id`           | approval_id, order_id, approver_id, created_at    |

## Security boundary

- The trigger function is `SECURITY DEFINER` with a fixed `search_path = pg_catalog, public`.
- `REVOKE ALL ON analytics_outbox FROM PUBLIC` — no direct read/write by application roles.
- `REVOKE ALL ON FUNCTION capture_outbox_event() FROM PUBLIC` — trigger cannot be called directly.
- The source write and outbox insert share the **same Postgres transaction** — no partial writes.
- Application roles receive no direct access to outbox rows; only the Delta runner (via the owner role) reads pending events.

## Failure model

1. **Source write succeeds, outbox insert fails** → the trigger function raises, the entire transaction rolls back. No inconsistency.
2. **Delta commit succeeds, acknowledgement fails** → the next run replays the same events. The MERGE on `lakebase_change_events` by `event_id` is idempotent; aggregates are recomputed from immutable raw events.
3. **Runner crashes mid-batch** → unacknowledged events remain pending. The next run replays them safely.
4. **Duplicate delivery** → `event_id` MERGE + `dedupe_key` UNIQUE prevent double-counting.

## Snapshot seed

On initial migration (004), one `snapshot` event is seeded for every existing
source row. The `dedupe_key` is `snapshot:{table}:{pk}`, so re-applying the
migration does not create duplicate events or triggers.

## Future migration to native Lakebase-CDF

When Databricks enables `CREATE PUBLICATION` on Lakebase instances, the outbox
can be replaced with native logical replication:

1. Create publication `lakebase_cdc` over the eight behavioural tables.
2. Use Lakeflow Connect or a CDC connector to consume the WAL stream.
3. Migrate the Delta runner to read from the CDC stream instead of polling the outbox.
4. Drop the trigger function, triggers, and outbox table.

The outbox pattern is intentionally compatible with this migration path: the
`event_id` ordering approximates WAL ordering, and the payload schema maps
directly to CDC before/after images.