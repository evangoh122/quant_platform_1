# BUILD-REQUEST: bronze-refresh — lane `options`

**Branch:** `slice/bronze-options` (its own worktree, off `slice/bronze-refresh`).
Full plan: `docs/BRONZE_REFRESH_PLAN.md` (written by Codex). Your lane is below, verbatim.
Three other builders run the other lanes **concurrently**. Edit **only** your lane's
exclusive files listed under "File ownership". Do not touch shared files.

**Execution:** this lane writes to live bronze tables. Run `--dry-run` first and paste its
report; then `--write`; then the verification queries. Bronze is **append-only** (a streaming
pipeline reads `bronze_ohlcv` as a stream): no UPDATE/DELETE/MERGE-update/overwrite, ever.
Never print secret values. Do not rebuild silver/gold, run the streaming pipeline, or use Lakebase.
Use the Bash tool's background caps generously; long downloads are expected.

**Commit your work** to `slice/bronze-options` and write `.agents/<you>/VERDICT-bronze-options.md`
with the dry-run report, write report, verification output, and anything you could not do.

---

## Objective and constraints

Refresh four independent Bronze sources through **2026-10-03**:

1. Equities
2. Options
3. CFTC Commitments of Traders
4. Federal Reserve/FRED series

All data-table writes must remain append-only. No Bronze `UPDATE`, `DELETE`, `OVERWRITE`, `replaceWhere`, or `MERGE WHEN MATCHED` is permitted. Incremental inputs must be filtered before append by either:

- skipping a source file already marked `SUCCESS`; and
- anti-joining candidate rows against the target table’s natural key.

The ingestion log may retain its existing status-update behavior because it is operational metadata, not a Bronze history table. Builders must use Databricks Connect serverless batch execution; do not configure streaming or interval triggers.

The legacy `etl/extract_*` modules are reference-only: their DuckDB writers are retired and raise when called. Production logic to reuse is in `notebooks/archive/00_project_setup.py` and `notebooks/01_ingest_market_data.py`.

## Common execution contract

Each lane must expose:

- `--dry-run`, which performs discovery, parsing, schema validation, deduplication, and counts but makes no table or log writes.
- `--write`, which repeats those checks and appends only the rows reported as new.
- Explicit `START_DATE` and `END_DATE` parameters, defaulting to the target table’s maximum source date plus one day and `2026-10-03`, respectively.
- A pre-write snapshot of target row count and maximum source date.
- A post-write report containing candidate count, duplicate/overlap count, appended count, new total row count, and new maximum source date.
- Failure propagation: a source file/date is never recorded as `SUCCESS` until all its target rows have appended and verification has passed.

For overlap safety, calculate new rows as a Spark left anti-join against keys projected from the existing target. Also call `dropDuplicates(key_columns)` on the incoming batch before that anti-join.

All timestamp handling is UTC internally. Session dates for equities remain New York dates. Preserve existing Gold conventions:

- Daily bars use the source bar’s day-start timestamp; their downstream availability remains 16:30 America/New_York.
- Minute `event_ts` is the bar start; downstream availability remains one bar later.
- Do not change timestamps to ingestion or availability timestamps in the Bronze market tables.

## File ownership and parallel work

| Builder/lane | Exclusive files |
|---|---|
| Equities | `notebooks/refresh_bronze_equities.py`, `tests/bronze/test_refresh_bronze_equities.py` |
| Options | `notebooks/refresh_bronze_options.py`, `tests/bronze/test_refresh_bronze_options.py` |
| COT | `notebooks/refresh_bronze_cot.py`, `tests/bronze/test_refresh_bronze_cot.py` |
| Fed | `notebooks/refresh_bronze_fed.py`, `tests/bronze/test_refresh_bronze_fed.py` |

The four builders must not edit any shared file, including:

- `conftest.py`
- `requirements.txt` or any `requirements*.txt`
- `etl/__init__.py`
- common database/configuration helpers
- existing production notebooks
- `docs/DATA_SCHEMAS.md` (not present on this branch)
- any pipeline, Silver, or Gold file

Dependencies used by these lanes—Spark, `boto3`, `requests`, and standard-library CSV/ZIP handling—already appear in the existing notebook code. If a missing dependency is discovered, the affected builder must report it instead of editing a shared requirements file.

Each test file must be self-contained and test pure parsing/key-selection helpers without importing a notebook that immediately starts a live ingestion.

---


# Lane 2: Options

## Ownership

Only edit:

- `notebooks/refresh_bronze_options.py`
- `tests/bronze/test_refresh_bronze_options.py`

## Existing code to reuse

For daily aggregates, copy and adapt the options implementation in `notebooks/archive/00_project_setup.py`:

- Massive S3 endpoint probing
- `stage_year`, but narrow it to individual missing dates rather than restaging whole years
- `OPRA_REGEX`
- `read_option_aggs`
- `shape_options`
- `clear_staged`
- existing target column selection

Replace the archived `write_year(... mode("overwrite").option("replaceWhere", ...))` logic entirely with append plus anti-join. Year overwrite is forbidden.

For IV/Greeks snapshots, adapt `ingest_polygon_options` from `notebooks/01_ingest_market_data.py`, including pagination of `client.list_snapshot_options_chain`, extraction of contract details, quotes, implied volatility, open interest, and Greeks when present. Correct its secret scope before use.

Do not call `etl/extract_options.py` or `etl/extract_polygon.run_polygon_options_etl`; both write through the retired DuckDB path.

## Sources and targets

| Dataset | Source | Target |
|---|---|---|
| Daily option aggregates | `us_options_opra/day_aggs_v1` | `bootcamp_students.evangoh_capstone.bronze_options_day` |
| IV/Greeks chain snapshots | Massive/Polygon REST options-chain snapshot | `bootcamp_students.evangoh_capstone.bronze_options_quotes` |

Daily aggregate schema remains:

`contract_symbol, underlying, expiry, strike, right, event_ts, event_date, event_year, open, high, low, close, volume, trade_count, timespan, source, source_file, ingest_ts`.

Use `right = 'CALL'/'PUT'`, `timespan = 'day'`, and `source = 'massive_flatfile'`.

For `bronze_options_quotes`, preserve existing columns wherever present:

`option_symbol, underlying, expiry, strike, right, participant_ts, bid, ask, midpoint, bid_size, ask_size, iv, open_interest, source, ingest_ts, raw_payload`.

If the live table already has Greek columns, populate them. Otherwise, do not evolve this existing table’s schema in this refresh merely to add Greeks; record that as follow-up schema work.

## Incremental window

Daily aggregates:

- Existing maximum: **2026-09-04**
- Requested discovery window: **2026-09-05 through 2026-10-03**, inclusive
- Runtime start: `date(max(event_ts)) + 1 day`

Snapshot table:

- Existing snapshot date: **2026-09-02**
- Logical missing window: **2026-09-03 through 2026-10-03**

The existing options-chain REST call is a current snapshot, not a historical snapshot API. Therefore this lane must not fabricate historical daily snapshots. On 2026-10-03 it may append only the snapshot actually returned by the provider and stamp it with the provider quote timestamp when available, otherwise the UTC retrieval time. The dates 2026-09-03 through the execution date are a documented coverage gap unless the installed entitlement exposes a genuine historical as-of snapshot endpoint. The builder may use such an endpoint only after verifying its response timestamps; it must not loop over dates while repeatedly calling the current-snapshot endpoint.

## Idempotency

Daily aggregate:

- Fast skip on `massive_ingestion_log` `SUCCESS` for `(source_file, 'us_options_opra/day_aggs_v1')`.
- Natural key: `(contract_symbol, event_ts, timespan)`.

Snapshot:

- Natural key: `(option_symbol, participant_ts)`.
- If the provider returns no quote timestamp and retrieval time must be used, normalize a run to one shared `snapshot_ts` and use `(option_symbol, snapshot_ts)`.
- Before re-running the same captured snapshot, persist and reuse an explicit run timestamp parameter; otherwise a new retrieval is legitimately a new snapshot, not a duplicate.
- `dropDuplicates` incoming keys and left anti-join against the target before append.

Do not treat `(option_symbol, calendar_date)` as the key because multiple legitimate intraday snapshots may exist.

## Dry-run and write sequence

1. Read both target counts and maxima.
2. Discover missing daily files by exact date.
3. Stage only those files to the existing UC Volume path.
4. Parse OPRA symbols and reject malformed contracts or null event timestamps.
5. Deduplicate and anti-join daily rows.
6. Retrieve the REST chain once in dry-run, count contracts and missing/usable quote timestamps, but write nothing.
7. Print that historical snapshot gaps are unrecoverable if no historical endpoint is available.
8. In write mode, repeat retrieval, anti-join, and append.
9. Clean staged daily files after successful parsing/write or after dry-run completes.
10. Never execute the archived per-year overwrite path.

## Verification

Daily:

```sql
SELECT COUNT(*), MAX(event_date)
FROM bootcamp_students.evangoh_capstone.bronze_options_day;
```

```sql
SELECT contract_symbol, event_ts, timespan, COUNT(*) AS n
FROM bootcamp_students.evangoh_capstone.bronze_options_day
WHERE event_date >= DATE '2026-09-05'
GROUP BY contract_symbol, event_ts, timespan
HAVING COUNT(*) > 1;
```

Snapshots:

```sql
SELECT COUNT(*), MAX(participant_ts)
FROM bootcamp_students.evangoh_capstone.bronze_options_quotes;
```

```sql
SELECT option_symbol, participant_ts, COUNT(*) AS n
FROM bootcamp_students.evangoh_capstone.bronze_options_quotes
WHERE participant_ts >= TIMESTAMP '2026-09-03'
GROUP BY option_symbol, participant_ts
HAVING COUNT(*) > 1;
```

Both duplicate checks must return zero rows. Confirm row deltas equal appended counts and report daily-aggregate freshness separately from snapshot freshness.

---


# Credentials and secret handling

Use only the measured Databricks secret scope:

```text
evangoh_capstone
```

Keys:

- `massive_s3_access_key`
- `massive_s3_secret_key`
- `polygon_api_key`

Rules:

- Never print secret values, prefixes, lengths, exception payloads containing request authorization, or configured client objects.
- Error messages may identify the missing scope/key name only.
- FRED and CFTC require no API key.
- Do not copy the archived setup cell that prints secret prefixes.
- Do not fall back to hard-coded credentials.

`notebooks/01_ingest_market_data.py` currently reads `capstone/polygon_api_key`. That scope does not exist. The options builder must use `evangoh_capstone/polygon_api_key` in its new lane file. Because existing files are off-limits for parallel ownership, correcting the original notebook is a separate follow-up change. No lane should reproduce the `"capstone"` scope bug.

# Coordinated run order

The lanes can build and dry-run concurrently because they own separate code files and target tables. Production writes should be controlled as follows:

1. Run unit tests for all four lane files.
2. Run all four lanes in `--dry-run`.
3. Review source discovery, entitlement failures, duplicate counts, revision conflicts, and predicted row deltas.
4. Run write mode:
   - Equities and options-daily may run concurrently only if their staging paths are source-specific and neither clears a shared parent directory.
   - Options REST snapshots can run after options-daily or concurrently if it uses no shared staging path.
   - COT and Fed may run concurrently with market lanes.
5. Run each lane’s verification queries immediately after its write.
6. Re-run every lane in dry-run mode. Expected new-row count is zero, except a genuinely newer REST options snapshot or newly published/revised upstream data.
7. Record unresolved failed files and entitlement gaps; do not force freshness by overwriting or synthesizing data.
8. `OPTIMIZE` may be scheduled separately after verification, but it is not required for correctness and must not be mixed into recovery logic.

# Operational risks and mitigations

| Risk | Mitigation |
|---|---|
| Massive entitlement window exposes keys that return 403 on `GET` | Probe access, classify 403 as an entitlement gap, continue other files, and never mark the inaccessible file successful. |
| Massive quota/rate limits | Process only missing dates, use bounded retries/backoff, avoid whole-year restaging, and retain progress per file. |
| A failed file appended some batches before failure | Anti-join every retry on the natural key; `SUCCESS` log skipping is only a fast path. |
| Existing `massive_ingestion_log` has 42 failed and 1 cancelled minute files | Reconsider them only when their dates are in the requested window or when explicitly running a repair mode; anti-join makes retry safe. Report older unresolved failures separately. |
| Existing options minute prefix has one failed record | Do not expand this effort to `bronze_options_minute`; this lane targets daily aggregates and quote snapshots only. |
| Full-market options data is very large | Stage and process individual dates, prune target anti-joins by event date, and avoid collecting data to the driver. |
| Current REST option snapshots cannot reconstruct missed dates | Append the real current snapshot only and report the historical coverage gap. Never relabel a current snapshot as historical. |
| CFTC release timing changes around holidays | Prefer official timestamps; otherwise use the conservative Monday fallback and preserve `release_ts`. |
| CFTC current-year files may revise earlier rows | Detect existing-key value conflicts and report them; do not overwrite. A versioned revision model is separate work. |
| FRED values are revised | Append changed values as new ingestion vintages; initial backfill availability is ingestion time. Use ALFRED in a future project for historical vintages. |
| FRED series have different publication lags | Never equate observation date with availability; use first-seen ingestion time until a release-calendar/ALFRED implementation exists. |
| Serverless rejects interval streaming triggers | Run bounded batch jobs only. |
| Schema drift | Use explicit schemas for stable derived columns, preserve raw CFTC strings, validate required columns before writes, and fail safely on incompatible changes. |

# Explicit non-goals

This effort does not include:

- Silver or Gold rebuilds
- running the existing Bronze-to-Silver streaming bundle
- any streaming trigger
- Lakebase reads or writes
- SEC EDGAR ingestion
- `bronze_economic_metrics` refresh
- options minute aggregates
- reconstructing historical options snapshots from current REST data
- CFTC revision-history schema redesign
- ALFRED vintage ingestion
- modifying trading-session or Gold availability conventions
- repairing the original SEC notebook’s unrelated `"capstone"` scope reference
- modifying shared dependency, fixture, configuration, or helper files

Silver/Gold refresh and validation must be planned as a separate follow-up after all four Bronze lanes pass their freshness, row-delta, and duplicate-key checks.


---


