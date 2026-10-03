===VERDICT START===
# VERDICT: bronze-options-check — DeepSeek
**Status:** APPROVED
**Round:** 1 (checker pass)

Independent check of `slice/bronze-options`. Code:
`notebooks/refresh_bronze_options.py`, tests
`tests/bronze/test_refresh_bronze_options.py`. Live run already performed by the
coordinator (written deltas match dry-run, zero duplicate keys, WRITE/OPTIMIZE-only
history). I did not modify production code or tests, and did not write to any table.

## Six check items

### 1. Append-only in every path + anti-join on full natural key — PASS
- Only three writes exist in the notebook and all are `mode("append")`:
  `saveAsTable(INGEST_LOG_TABLE)` at line 421 (operational metadata, allowed),
  `saveAsTable(DAY_TABLE)` at line 673, `saveAsTable(QUOTES_TABLE)` at line 831.
- No `overwrite`, `replaceWhere`, `mergeInto`, `createOrReplace`, `DELETE`, or
  `MERGE` anywhere in the file (grepped).
- Daily anti-join uses the full natural key `DAY_KEY_COLUMNS =
  ["contract_symbol","event_ts","timespan"]` (line 74) via `_anti_join_new`
  (lines 580-594): `dropDuplicates(key_columns)` then `left_anti` on the same key.
- Snapshot uses `SNAPSHOT_KEY_COLUMNS = ["option_symbol","participant_ts"]`
  (line 75) with `dropDuplicates` (line 816) and `left_anti` (line 823) on the same key.
- First-time table creation: N/A for this lane — both targets pre-exist (plan
  states existing max `2026-09-04` / `2026-09-02`). There is no CREATE TABLE logic,
  so "append-only first-time creation" does not apply to options. (Non-blocking: if
  a table were absent the pre-read `spark.table(...)` at lines 585/818 would raise
  rather than silently create.)

### 2. SUCCESS only after rows landed + verification — PASS (minor note)
- Daily: `log_start` writes RUNNING (line 652), append happens (line 673), and only
  then `log_finish(..., SUCCESS, new)` (line 675). On exception, `log_finish(...,
  FAILED)` (line 684). Because the Delta append at line 673 is synchronous/atomic,
  reaching line 675 guarantees the rows are committed; a throwing append is caught
  and marked FAILED, never SUCCESS.
- Non-blocking note: there is no separate post-write "verification query" re-reading
  the target keys before marking SUCCESS (the plan's daily step 7 wording). The
  atomic append's success serves as verification; coordinator's live duplicate checks
  returned zero. Also, a fresh file yielding `new == 0` (line 678) is marked SUCCESS
  with 0 rows — correct for a true duplicate, but if a source schema drift made every
  incoming row filter to null it would be marked SUCCESS with 0 without a
  `_resolve_write_columns` check (that check only runs when `new > 0`, line 671).
  Low-probability data-quality edge, not a write-path defect.

### 3. Timestamps not altered in bronze — PASS
- `event_ts` is derived from the source `window_start` nanosecond epoch
  (lines 459-461), not from ingestion time. `event_date`/`event_year` are derived
  from `event_ts` (lines 474-475). `ingest_ts` is a separate column (line 630).
  Bars keep their source start time; nothing is relabelled to ingestion/availability time.
- Snapshot `participant_ts` uses the provider sip/participant timestamp and only
  falls back to retrieval time when the provider supplies none (lines 284-287,
  `resolve_snapshot_ts` 238-244), matching the plan's documented fallback.

### 4. Credentials from scope evangoh_capstone, never printed — PASS (minor note)
- `SECRET_SCOPE = "evangoh_capstone"` (line 63); `_get_secret` reads via
  `dbutils.secrets.get` or `WorkspaceClient.secrets.get_secret` (lines 353-359).
  The `capstone` scope bug is not reproduced.
- Secret values are only ever passed as constructor args (`_make_s3_client` 370-380,
  `_make_polygon_client` 725-727); never printed, never interpolated, never in a
  DataFrame. `main` prints only exception type names for the polygon probe (line 932).
- Minor note: `_detect_s3` prints `{type(exc).__name__}: {exc}` (line 398), and
  `log_finish` stores `str(error_message)[:4000]` (line 441). This is the explicit
  round-4 instruction (surface the real cause, never secrets). The secret *values*
  are not present in these payloads; boto3 signature errors could include the
  access-key *id* prefix in rare cases but never the secret key.

### 5. Tests call production functions; would they catch a broken anti-join? — GAP (non-blocking)
- Tests import the real module (`from notebooks import refresh_bronze_options as m`)
  and call production functions: `parse_opra_symbol`, `ns_to_ts`, `as_float`,
  `as_int`, `date_window`, `s3_key_for_date`, `resolve_snapshot_ts`,
  `shape_quote_row`, `_right_from_contract_type`, `_resolve_write_columns`,
  `_stage_file`, `trading_days`, `_run_daily`. No test-local reimplementation.
- BUT: no test exercises `_anti_join_new` (the dedup + left-anti-join), and the one
  `_run_daily` test (tests/bronze/test_refresh_bronze_options.py:353-379) only
  covers the "missing file -> failed" branch (head_object raises before anti-join).
  So the suite would NOT fail if the dedup/anti-join broke.
- Proof (mutated copy under /tmp, worktree untouched): I copied
  `notebooks/refresh_bronze_options.py` to `/tmp/bronze_mut/notebooks/`, replaced
  `dedup = incoming_df.dropDuplicates(key_columns)` with `dedup = incoming_df` and
  `return dedup.join(target_keys, key_columns, "left_anti")` with `return dedup`
  (verified markers at lines 584/594 of the copy), then ran the unmodified test file
  against it: `PYTHONPATH=/tmp/bronze_mut python3 -m pytest test_refresh_bronze_options.py -q`
  → **30 passed**. The mutation (removing both dedup and anti-join) is undetectable
  by the current suite.
- Recommendation (not a live defect — anti-join is correct and was empirically
  verified live): add a unit test for `_anti_join_new` asserting duplicate keys are
  dropped and already-present keys are excluded.

### 6. Re-run safety: --write again appends 0 rows — PASS (daily); snapshot by design
- Daily: after a clean run every file has a `SUCCESS` row, so `already_ingested`
  (lines 407-412) skips them all on re-run → 0 candidates, 0 appended. For a prior
  partial/FAILED file, the anti-join still prevents re-appending existing keys.
- Snapshot: re-run retrieves a fresh current snapshot with a new `snapshot_ts`, which
  is a legitimately new snapshot (plan: "a new retrieval is legitimately a new
  snapshot, not a duplicate"); the run timestamp is not persisted/reused
  (line 793 uses `datetime.now()` each run). This is documented behaviour, and the
  snapshot path is currently blocked anyway (invalid `polygon_api_key` per round-3).

## Checks run
- `python3 -m pytest tests/bronze/test_refresh_bronze_options.py -q` → **30 passed in 0.13s** (pass)
- grep for `overwrite|replaceWhere|mergeInto|createOrReplace|DELETE|MERGE` in the notebook → none in write paths (pass)
- `PYTHONPATH=/tmp/bronze_mut python3 -m pytest test_refresh_bronze_options.py -q` (anti-join + dedup removed in /tmp copy) → **30 passed** (documents the item-5 coverage gap)

## Verdict
APPROVED. All six hard requirements (append-only, natural-key anti-join, SUCCESS
semantics, timestamp fidelity, secret handling, re-run idempotency) hold. One
non-blocking hardening gap: `_anti_join_new` is untested (item 5, proven above).
No blocking defects.
===VERDICT END===
