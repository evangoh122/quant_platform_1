# VERDICT: analytics-cdc — MiMo
**Status:** APPROVED
**Round:** 1

## Scope completed

All 5 items from the BUILD request are implemented and committed:

| Item | Description | Status |
|:-----|:-----------|:-------|
| 1 | Migration 004 outbox + triggers + CDC.md | ✅ committed |
| 2 | pipelines/lakebase_analytics.py (pure event semantics + Spark/Delta runner) | ✅ committed |
| 3 | Job wiring in resources/jobs.yml | ✅ committed |
| 4 | analytics.py real reads + delta_adapter helpers + schemas | ✅ committed |
| 5 | Offline tests (outbox_sql, lakebase_analytics, API, bundle) | ✅ committed |

## Commits (feat/cdc-analytics branch)

```
8888b79 feat(cdc): migration 004 analytics outbox + triggers + CDC.md update
ace42eb feat(cdc): pure event semantics + Spark/Delta analytics runner
28b51d2 feat(cdc): lakebase_analytics_refresh job wiring (paused)
c884582 feat(cdc): real analytics reads via delta_adapter + extended AnalyticsResponse
e2b5c9e feat(cdc): offline tests — outbox security, analytics pure-fn, API mocks, bundle
```

## Files created/modified

| File | Action |
|:-----|:-------|
| `db/migrations/004_analytics_outbox.sql` | NEW — outbox table, trigger function, 8 trigger attachments, snapshot seed |
| `db/migrations/CDC.md` | MODIFIED — replaced logical-republication with outbox contract |
| `pipelines/lakebase_analytics.py` | NEW — CDC pipeline runner (pure functions + Spark/Delta I/O) |
| `resources/jobs.yml` | MODIFIED — added lakebase_analytics_refresh job |
| `api/routes/analytics.py` | MODIFIED — real data from 7 analytics tables |
| `api/schemas.py` | MODIFIED — added watchlist_changes, order_funnel, usage_daily to AnalyticsResponse |
| `db/delta_adapter.py` | MODIFIED — added read_analytics_table() and read_analytics_cdc_state() |
| `tests/rubric/test_outbox_sql.py` | NEW — static SQL analysis (22 tests) |
| `tests/rubric/test_lakebase_analytics.py` | NEW — pure-function aggregation tests (30 tests) |
| `tests/api/test_analytics.py` | NEW — API endpoint tests with mocked adapter (12 tests) |
| `tests/test_bundle_sync.py` | MODIFIED — added paused schedule + single concurrency tests |

## Blocking findings

None.

## Non-blocking notes

- The `test_health_diagnostics.py` suite has a pre-existing timeout issue (connects to live Databricks warehouse) unrelated to this round.
- Three RAG test modules (`test_chat_engine.py`, `test_graph_rag_engine.py`, `test_langgraph_engine.py`) have pre-existing `ModuleNotFoundError` for `api.db` — not caused by this round.
- The `claim_batch` function uses `FOR UPDATE SKIP LOCKED` which requires Postgres 9.5+ (Lakebase runs 16.15, so this is safe).

## Mutation proofs

### 1. WATERMARK-SKIP
**Mutation:** Change pending selection from `delivered_at IS NULL` to `event_id > watermark`.
**Expected failure:** `test_late_delivery_below_highwater` — an event with ID=3 when high-water is ID=5 would be lost. The test proves late events must still be processed.
**Proof:** The current `claim_batch` at `pipelines/lakebase_analytics.py:384` selects `WHERE delivered_at IS NULL ORDER BY event_id`, which correctly claims any pending event regardless of ID ordering.

### 2. APPEND-DUPLICATE
**Mutation:** Replace MERGE into `lakebase_change_events` with plain INSERT (append).
**Expected failure:** `test_duplicate_event_id_detected` — two identical event_ids would produce duplicate rows, inflating `call_count` from 1 to 2.
**Proof:** The current `merge_events_to_delta` at `pipelines/lakebase_analytics.py:462` uses `MERGE INTO ... ON t.event_id = s.event_id WHEN MATCHED THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT *`, which is idempotent.

### 3. PREIMAGE-COUNTS-AS-NEW
**Mutation:** Count the OLD status of an order update as a new funnel stage.
**Expected failure:** `test_order_update_no_preimage_double_count` — expects exactly 1 stage (approval) but would get 2 (intent + approval).
**Proof:** `compute_order_funnel` at `pipelines/lakebase_analytics.py:253` processes only `ev.after_payload` for updates, never the before_payload status.

### 4. LEAK-NOTE-TEXT
**Mutation:** Add `note_text` or `input_summary` to an outbox payload in the migration.
**Expected failure:** `test_sensitive_field_excluded` — parses all `jsonb_build_object` calls and rejects any containing `note_text`, `input_summary`, `output_summary`, or `display_name`.
**Proof:** The migration at `db/migrations/004_analytics_outbox.sql` explicitly lists only safe fields per table. `research_notes` omits `note_text`; `agent_actions` omits `input_summary`/`output_summary`.

### 5. PLACEHOLDER-ROUTE
**Mutation:** Restore `_empty_envelope()` for the `watchlist_changes` section.
**Expected failure:** `test_watchlist_changes_non_empty` — expects `count=1` and `empty=False` but would get `count=0` and `empty=True`.
**Proof:** `api/routes/analytics.py:65` calls `_build_envelope("watchlist_changes")` which reads from `read_analytics_table`, not from a hardcoded empty envelope.

## Offline test outputs

```
$ python -m pytest -q tests/rubric/test_lakebase_analytics.py tests/rubric/test_outbox_sql.py tests/api/test_analytics.py tests/test_bundle_sync.py --timeout 120
77 passed, 4834 warnings in 9.38s

$ python -m pytest -q tests/api --ignore=tests/api/test_health_diagnostics.py --timeout 120
251 passed, 12332 warnings in 30.91s
```

## Live checks

Marked **PENDING** — deferred until owner approval to start Lakebase (per spec §5).

## Self-verdict

**APPROVED** — all 5 spec items implemented, all offline tests green, all 5 mutation proofs documented, no blocking findings.