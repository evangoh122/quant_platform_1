# VERDICT: analytics-cdc — DeepSeek
**Status:** CHANGES_REQUESTED
**Round:** 1

===VERDICT START===

## Blocking findings

### 1. Migration trigger function references `NEW.watchlist_id` on all 8 tables — breaks 7 of 8 write paths
- `db/migrations/004_analytics_outbox.sql:56-93`
- The `IF TG_OP = 'INSERT'` branch executes `_pk := NEW.watchlist_id;` (line 58) and builds a
  watchlist-shaped `jsonb_build_object('watchlist_id', NEW.watchlist_id, ...)` **before** the
  `IF TG_TABLE_NAME = 'signals'` branch. Same for `UPDATE` (line 68) and `DELETE` (line 85, `OLD.watchlist_id`).
- `NEW`/`OLD` are typed to the triggering table's row. Only `watchlists` has a `watchlist_id` column
  (`db/migrations/001_operational_schema.sql:26-34`). `signals`, `orders`, `executions`, `positions`,
  `agent_actions`, `research_notes`, `approvals` do not.
- **Failure scenario:** `INSERT INTO signals (...) VALUES (...)` fires `capture_outbox_event()`, which
  evaluates `NEW.watchlist_id` and raises `record "new" has no field "watchlist_id"`. The trigger raises
  inside the same transaction, so the source write rolls back. Every write to 7 of the 8 behavioural
  tables fails; the outbox never populates and the app's operational write path is broken.
- The offline `tests/rubric/test_outbox_sql.py` cannot catch this because it only text-parses the SQL.

### 2. `UNIQUE (dedupe_key)` collides on every repeated UPDATE — order funnel state machine cannot advance
- `db/migrations/004_analytics_outbox.sql:33` declares `CONSTRAINT analytics_outbox_dedupe_uq UNIQUE (dedupe_key)`.
- The trigger inserts `dedupe_key = _op || ':' || TG_TABLE_NAME || ':' || _pk` (`:444`). For an UPDATE
  that is `update:orders:<order_id>`, which is identical on the second update of the same row.
- **Failure scenario:** an order transitioning `PENDING_APPROVAL → APPROVED` (update #1) writes
  `update:orders:O1`; the next transition `APPROVED → SUBMITTED` (update #2) regenerates
  `update:orders:O1` and violates `analytics_outbox_dedupe_uq`, rolling back the second update.
  The funnel depends on successive status transitions, so it stalls after the first update.
- The snapshot seeds (`:489-612`) are correctly idempotent (`ON CONFLICT ... DO NOTHING`); the trigger's
  reuse of the same `update:{table}:{pk}` key is the defect.

### 3. Migration 004 is not idempotent on re-apply — `CREATE TRIGGER` has no `IF NOT EXISTS`
- `db/migrations/004_analytics_outbox.sql:454-484` emit plain `CREATE TRIGGER trg_outbox_* ...`.
- PostgreSQL has no `CREATE TRIGGER IF NOT EXISTS` (the header comment at `:6` claims it does). There is
  no `DROP TRIGGER IF EXISTS` guard.
- **Failure scenario:** re-running the migration SQL directly fails with
  `trigger "trg_outbox_watchlists" for relation "watchlists" already exists`. The runner
  (`db/migrate.py`) masks this by skipping recorded versions, but the explicit acceptance criterion
  "idempotent on re-apply" and the §5 live-check "Reapply and prove … unchanged" are not met by the SQL.

### 4. Two of the four named checker mutations do NOT fail any test
- Re-run in disposable copies (`git archive HEAD | tar -x`). Empirical results:
  - **WATERMARK-SKIP** (changed `claim_batch` pending selection to `event_id > MAX(delivered event_id)`):
    `python3 -m pytest -q tests/rubric tests/api --timeout 60` → **0 analytics failures** (only an unrelated,
    flaky `tests/api/test_resilience.py::test_first_request_bounded_when_pool_hangs`, which passes on re-run).
  - **APPEND-DUPLICATE** (replaced `MERGE INTO lakebase_change_events` with `INSERT ... SELECT *`):
    → **359 passed**.
- Root cause: `claim_batch` (`pipelines/lakebase_analytics.py:378-407`) has no test; the "duplicate" test
  `tests/rubric/test_lakebase_analytics.py:343-354` explicitly asserts the **inflated** count
  (`call_count == 2`) and documents "the MERGE on Delta handles dedup at the event level", so it cannot
  distinguish MERGE from append. This violates the request's "each must FAIL a test" requirement and leaves
  the two most safety-critical behaviours (no lost low-ID events; idempotent replay) unprotected.
- (The other two mutations behave correctly: **LEAK-NOTE-TEXT** fails
  `tests/rubric/test_outbox_sql.py::test_sensitive_field_excluded[note_text]`; **PLACEHOLDER-ROUTE** fails
  `tests/api/test_analytics.py::TestAnalyticsEndpoint::test_watchlist_changes_non_empty`.)

## Non-blocking notes

- `db/delta_adapter.py:504-518` — `read_analytics_table` wraps the warehouse/spark read in `try/except:
  return []`. A genuine backend outage therefore returns `[]`, which `api/deps.py:read_delta` maps to
  `"empty"` rather than `"unavailable"`. The `unavailable` envelope state is unreachable in production for
  these sections (the API test only passes because it mocks `read_analytics_table` to raise directly).
- `pipelines/lakebase_analytics.py:492,515` — date lists are built with f-string interpolation into Spark
  SQL (`date(occurred_at) IN (...)`). Values are machine-generated `%Y-%m-%d` (not user input), so no
  injection risk, but it is string-built SQL. Postgres queries correctly use `%s` placeholders (`:385-399`,
  `:423-431`).
- `db/migrations/004_analytics_outbox.sql:103` stores `NEW.probability` as numeric JSONB while the snapshot
  seed at `:510` stores `probability::TEXT`. No functional impact on the four analytics tables, but the two
  paths produce inconsistent payload types.
- `pipelines/lakebase_analytics.py:587` uses a per-run `run_id` as the MERGE key, so `analytics_cdc_state`
  accumulates a row per run; `db/delta_adapter.py:521-538` reads it with `LIMIT 1` and no `ORDER BY`, so the
  "latest" state is not guaranteed.

## Checks run

- `python3 -m pytest -q tests/rubric tests/api --timeout 60` → **359 passed** (matches Claude's report).
- Mutation WATERMARK-SKIP (disposable copy) → no analytics/rubric test fails (only flaky resilience test).
- Mutation APPEND-DUPLICATE (disposable copy) → `359 passed`.
- Mutation LEAK-NOTE-TEXT (disposable copy) → `FAILED test_sensitive_field_excluded[note_text]`.
- Mutation PLACEHOLDER-ROUTE (disposable copy) → `FAILED test_watchlist_changes_non_empty`.

===VERDICT END===
