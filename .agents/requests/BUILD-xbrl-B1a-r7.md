# BUILD-xbrl-B1a round 7 — bugs found by Claude's LIVE run (all fakes passed, Spark rejected the writes)

You are MiMo. Branch `feat/xbrl-fundamentals` (stay on it). LF endings, never touch `.agents/dispatch.sh`, no Databricks.
Shell rule: if a command needs quoting, write it to `/home/jianj/code/qp1-xbrl/.agentlogs/<name>.sh` and run exactly
`wsl -d Ubuntu -- bash /home/jianj/code/qp1-xbrl/.agentlogs/<name>.sh`. No .ps1/.bat, no PowerShell wrappers, nothing in C:\temp.
COMMIT per item; verdict `.agents/mimo/VERDICT-xbrl-B1a-r7.md`.
Live run: `python3 -m pipelines.ingest_sec_companyfacts --tickers NVDA,XOM --run-id ... --catalog bootcamp_students --schema evangoh_capstone`
1. Every CIK failed: `[CANNOT_DETERMINE_TYPE] Some of types cannot be determined after inferring` — `spark.createDataFrame(rows)` infers types and
   all-null columns (period_start/instant/frame/…) cannot be inferred. Define ONE explicit `StructType` for bronze (exact names/types of the DDL in
   Plan B §2.2 as created: ingest_run_id string, ingested_at timestamp, …, value_decimal double, fiscal_year int, …) and ALWAYS pass it to
   createDataFrame; coerce values to those types before (timestamps as datetime, ints as int).
2. Manifest write failed: `[DELTA_METADATA_MISMATCH]` — the DataFrame has `http_status` but the table created by the DDL does not (live table
   sec_companyfacts_ingest_log has: ingest_run_id, cik, ticker, fetch_status, attempt_count, payload_hash, payload_bytes, fact_count, started_at,
   completed_at, error_category, error_message, logged_at). Add `http_status int` to the manifest DDL AND an explicit manifest StructType; when the
   existing table lacks a column, run `ALTER TABLE … ADD COLUMNS (http_status INT)` before writing (idempotent).
3. Tests (no Spark needed): the bronze and manifest StructTypes equal the DDL column lists (names, order, types) — a single source of truth;
   a flattened row with every optional field None converts to a tuple that matches the StructType (no inference anywhere: grep-style test that
   every createDataFrame call passes a schema). Mutation for the checker: drop the schema argument → test fails; remove http_status from the
   DDL → test fails.
4. Also: the local CIK cache path defaults to /Volumes (warning "Permission denied: '/Volumes'" when run outside Databricks) — fall back to a
   temp dir when the default path is not writable, with a test.
