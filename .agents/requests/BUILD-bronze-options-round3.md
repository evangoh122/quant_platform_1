# BUILD-REQUEST: bronze-options — ROUND 3 (the source IS accessible)

**Branch:** `slice/bronze-options` · **Builder:** MiMo · **Checkers:** Claude, then DeepSeek

## Your round-2 conclusion was wrong — measured by the coordinator
You reported "Massive flat-files: access probe FAILED on all endpoints (403)". The coordinator
tested the same credentials and **all of these list AND download successfully**:

```
endpoint  https://files.massive.com   bucket  flatfiles   signature s3v4
us_options_opra/day_aggs_v1/2026/09/   21 files, last 2026-09-30.csv.gz   HEAD ok
us_options_opra/day_aggs_v1/2026/10/    1 file,  last 2026-10-01.csv.gz   HEAD ok
```

Credentials: secret scope **`evangoh_capstone`** (not `capstone`, which does not exist), keys
`massive_s3_access_key` and `massive_s3_secret_key`. Read them with
`databricks secrets get-secret evangoh_capstone <key>` (value is base64) or `dbutils.secrets.get`.
Never print them. Find out why your probe failed (wrong scope? wrong endpoint/bucket? the REST
key used for S3?) and state the cause in your verdict.

**Genuinely broken:** the Polygon/Massive **REST** key `polygon_api_key` (13 characters; real keys
are 32) returns HTTP 401 "Unknown API Key" from both api.polygon.io and api.massive.com. So the
**IV/greeks snapshot into `bronze_options_quotes` is blocked** — skip it, report it, do not fake it.

## Do
1. **Refresh `bronze_options_day`** from `us_options_opra/day_aggs_v1` for every trading day
   after its current max (2026-09-04) through the latest file (2026-10-01). `--dry-run` first
   (paste it), then `--write`, then verification (new max date, row delta, zero duplicate keys).
   Append-only.
2. **Fail loudly on schema mismatch.** `_resolve_write_columns` currently *drops* any column the
   live table lacks — silent data loss. Instead: if incoming columns ≠ table columns (names or
   types), raise with the diff. Only reorder columns to match; never drop.
3. Normalise option `right` to the live table's existing encoding (`'call'`/`'put'`) — do not
   introduce mixed `'C'/'P'` values.

Edit only `notebooks/refresh_bronze_options.py` and `tests/bronze/test_refresh_bronze_options.py`.
LF line endings. Do not create files in the Databricks workspace. **Commit your work.**
Write `.agents/mimo/VERDICT-bronze-options-round3.md` with real dry-run, write and verification output.
