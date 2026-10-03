# VERDICT: bronze-options — DeepSeek

**Status:** BLOCKED
**Round:** 1

## Summary

Lane `options` code is complete, unit-tested, and the append/anti-join/dedup
Spark path is validated end-to-end against a scratch table. However, the actual
Bronze refresh could not be executed because **both source channels are
unavailable**:

1. **Massive flat files** return `403 Forbidden` on every endpoint and prefix
   (`files.massive.com`, `files.polygon.io`) — including the equities prefix
   and the archived 2025 probe key — so the daily aggregate entitlement is
   down or the S3 keys in `evangoh_capstone` are revoked.
2. **Polygon REST** returns `{"status":"ERROR","error":"Unknown API Key"}` for
   `evangoh_capstone/polygon_api_key`, so the chain snapshot cannot be
   retrieved.

Per the plan, a 403 is classified as an entitlement gap and the builder must
not force freshness or synthesize data, and must not set/hard-code secrets.
Nothing was appended, nothing was overwritten, and nothing was marked `SUCCESS`.

## Blocking findings

- **External — Massive entitlement (403).** `s3.list_objects_v2` on
  `us_options_opra/day_aggs_v1/` (and on `us_stocks_sip/`, and the root) returns
  403 for both `files.massive.com` and `files.polygon.io` with the
  `evangoh_capstone` S3 keys. → No daily aggregate file for
  `2026-09-05 .. 2026-10-03` can be staged, so `bronze_options_day` cannot
  advance past its current `max(event_date) = 2026-09-04`.
- **External — Polygon key invalid.** `RESTClient` with
  `evangoh_capstone/polygon_api_key` returns `Unknown API Key`. → The current
  options-chain snapshot cannot be retrieved, so `bronze_options_quotes` cannot
  advance past `max(participant_ts) = 2026-09-02T00:36:24.930Z`.

These are credential/entitlement failures outside the builder's authority
(the plan forbids falling back to other scopes or hard-coded credentials).
Restoring the massive S3 entitlement and a valid Polygon key unblocks the lane
with no code changes.

## Non-blocking notes

- `bronze_options_quotes` (live) encodes `right` as lowercase `'call'/'put'` and
  `source='massive'`, while the plan's reference `ingest_polygon_options` emits
  `'C'/'P'` and `'polygon'`. The new snapshot writer follows the reference and
  the column comment (`C = call, P = put`). This introduces a mixed encoding in
  the existing table; a follow-up normalization is recommended (out of scope).
- The live `bronze_options_quotes` column is `implied_volatility` (not `iv` as
  named in the request), and the table already carries Greek columns
  (`delta/gamma/theta/vega`). The writer maps to the actual columns and
  populates Greeks when present, per the plan.
- The installed `polygon-api-client` (1.16.3) signature is
  `list_snapshot_options_chain(underlying_asset, params=...)`; the archived
  notebook's `limit=` kwarg no longer exists. The writer uses
  `params={"limit": 250}`.
- Daily aggregates have **no** existing `massive_ingestion_log` rows (the
  archived options path never logged), so the `SUCCESS` fast-skip is a no-op
  until the first successful write; the anti-join remains the real safety net.
- Daily staging uses UC Volume + `spark.read.csv` (the archived options pattern,
  avoids driver collection); under Databricks Connect serverless it uploads to
  the Volume via the SDK Files API and reads back with Spark. Verified with a
  synthetic round-trip.
- Snapshot has no date window (current-snapshot endpoint only), so
  `2026-09-03 .. execution-date` remains a documented coverage gap.

## Deliverables

- `notebooks/refresh_bronze_options.py` — `--dry-run` / `--write`,
  `--start-date` / `--end-date`, append-only, `dropDuplicates` + left anti-join
  on `(contract_symbol, event_ts, timespan)` and `(option_symbol,
  participant_ts)`, parameterized SQL only, no secret printing.
- `tests/bronze/test_refresh_bronze_options.py` — 22 self-contained tests over
  pure parsing/key-selection helpers (no Spark/S3/Databricks on import).

## Dry-run report (paste)

```
==============================================================================
PRE-WRITE SNAPSHOT
==============================================================================
  bronze_options_day   : rows=146,117,971 max_event_date=2026-09-04
  bronze_options_quotes: rows=61,882 max_participant_ts=2026-09-02 08:36:24.930278
==============================================================================
MASSIVE FLAT-FILES: access probe FAILED on all endpoints (403 / entitlement gap).
No daily aggregate files can be staged or read this run; the anti-join prevents
any partial writes. Nothing was marked SUCCESS. Classifying the whole window as
an entitlement gap.
==============================================================================
POLYGON REST SNAPSHOT: access probe FAILED (BadResponse).
No snapshot can be retrieved; the current snapshot coverage gap (2026-09-03 ..
execution date) remains unrecoverable without a historical as-of endpoint.
Nothing was appended.
==============================================================================
REFRESH COMPLETE (dry-run)
==============================================================================
```

## Write report (paste)

`--write` re-ran the same probes and appended **0 rows** to both targets
(correct: no synthetic data, no overwrite, no `SUCCESS` records written).
Pre-write snapshot identical to the dry-run (146,117,971 / 61,882), confirming
no accidental writes.

## Verification output (paste)

Duplicate-key checks over the requested window — both return **zero rows**
(no data exists past the current maxima, and nothing was appended):

```sql
SELECT contract_symbol, event_ts, timespan, COUNT(*) AS n
FROM bootcamp_students.evangoh_capstone.bronze_options_day
WHERE event_date >= DATE '2026-09-05'
GROUP BY contract_symbol, event_ts, timespan
HAVING COUNT(*) > 1;          -- 0 rows

SELECT option_symbol, participant_ts, COUNT(*) AS n
FROM bootcamp_students.evangoh_capstone.bronze_options_quotes
WHERE participant_ts >= TIMESTAMP '2026-09-03'
GROUP BY option_symbol, participant_ts
HAVING COUNT(*) > 1;          -- 0 rows
```

Post-write counts unchanged from pre-write: `bronze_options_day=146,117,971`,
`bronze_options_quotes=61,882`. Row delta == appended count (0 == 0).

## Checks run

- `python3 -m pytest tests/bronze/ -q` → **24 passed, 10 skipped**
- `python3 -m pytest tests/bronze/test_refresh_bronze_options.py -q` → **22 passed**
- `python3 notebooks/refresh_bronze_options.py --dry-run` (Databricks Connect
  serverless) → pre-write snapshot + entitlement-gap classification (pasted above)
- `python3 notebooks/refresh_bronze_options.py --write` → 0 appended (sources down)
- Scratch validation (`validate_daily.py`): `_shape_day` + `_anti_join_new` +
  append against a temp table → candidate=3 (incl. intra-file dup), new=1,
  re-run new=0, duplicate keys=0; **all assertions passed**; scratch table/Volume
  cleaned up.
- `grep -nE 'overwrite|replaceWhere|MERGE|DELETE|INSERT INTO|mode\("overwrite"'` → none
- `grep -nE 'spark.sql\(f|sql\(f'` → none (all SQL values parameterized via `args=` or DataFrame API)
- `grep -nE 'print.*(secret|access_key|api_key|token)'` → none

## Could not do

- Append any daily aggregate rows (Massive 403 entitlement gap).
- Append any chain snapshot (Polygon `Unknown API Key`).
- Advance `max(event_date)` past 2026-09-04 or `max(participant_ts)` past
  2026-09-02T00:36:24.930Z.
- Validate the snapshot `right`/`source` encoding against a live provider
  response (key invalid), so that remains a documented follow-up.
