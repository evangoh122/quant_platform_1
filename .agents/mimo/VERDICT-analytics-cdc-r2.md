# VERDICT: analytics-cdc-r2 — MiMo
**Status:** APPROVED
**Round:** 2

## Blocking findings
(none — all 4 DeepSeek blocking findings resolved)

## Fixes applied

### 1. Per-table trigger functions (Finding #1)
- **Commit:** `16a8699`
- Replaced shared `capture_outbox_event()` with 8 per-table functions:
  `capture_outbox_watchlists()`, `capture_outbox_signals()`, `capture_outbox_orders()`,
  `capture_outbox_executions()`, `capture_outbox_positions()`, `capture_outbox_agent_actions()`,
  `capture_outbox_research_notes()`, `capture_outbox_approvals()`
- Each function references ONLY its own table's columns via NEW/OLD
- Each function has SECURITY DEFINER, fixed search_path, and revoked PUBLIC execute
- Verified by `test_trigger_column_references_match_table_schemas` which parses
  migrations 001-003 for column definitions and validates every NEW/OLD reference

### 2. Dedupe key uniqueness (Finding #2)
- **Commit:** `16a8699`
- Trigger-generated events now use `dedupe_key = NULL` (Postgres UNIQUE allows multiple NULLs)
- Snapshot seeds retain `snapshot:<table>:<pk>` for ON CONFLICT dedup
- Successive UPDATEs on the same row each produce their own outbox row
- Verified by `test_trigger_events_use_null_dedupe_key`

### 3. Idempotent re-apply (Finding #3)
- **Commit:** `16a8699`
- Added `DROP TRIGGER IF EXISTS trg_outbox_<table> ON <table>;` before each `CREATE TRIGGER`
- Fixed header comment (Postgres has no CREATE TRIGGER IF NOT EXISTS)
- Verified by `test_drop_trigger_if_exists` (parametrized over all 8 tables)

### 4. Mutation-catching tests (Finding #4)
- **Commit:** `3a97fbb`
- `test_claim_batch_selects_pending_by_null_delivered_at`: parses claim_batch SQL
  to verify `WHERE delivered_at IS NULL` — catches WATERMARK-SKIP mutation
- `test_merge_events_uses_merge_into`: parses merge_events_to_delta SQL to verify
  `MERGE INTO` — catches APPEND-DUPLICATE mutation
- `test_trigger_column_references_match_table_schemas`: validates every NEW/OLD
  reference against actual table schemas — catches cross-table column references

### 5. Pipeline import fix (bonus)
- **Commit:** `b633537`
- Guarded `CHANGE_EVENTS_SCHEMA` and `STATE_SCHEMA` with `if _has_pyspark:` so the
  module is importable without pyspark (required for pure-function tests)

## Non-blocking notes
- `dispatch.sh` was already modified (mode change) before this round; not touched.

## Checks run
- `python3 -m pytest -q tests/rubric/test_outbox_sql.py` → **43 passed**
- `python3 -m pytest -q tests/rubric tests/api` → **377 passed, 1 failed (pre-existing: `test_warehouse_available_detects_installed_connector` — databricks-sql-connector not installed in test env), 2 skipped**