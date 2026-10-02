# BUILD-REQUEST: bronze-refresh — lane `fed`

**Branch:** `slice/bronze-fed` (its own worktree, off `slice/bronze-refresh`).
Full plan: `docs/BRONZE_REFRESH_PLAN.md` (written by Codex). Your lane is below, verbatim.
Three other builders run the other lanes **concurrently**. Edit **only** your lane's
exclusive files listed under "File ownership". Do not touch shared files.

**Execution:** this lane writes to live bronze tables. Run `--dry-run` first and paste its
report; then `--write`; then the verification queries. Bronze is **append-only** (a streaming
pipeline reads `bronze_ohlcv` as a stream): no UPDATE/DELETE/MERGE-update/overwrite, ever.
Never print secret values. Do not rebuild silver/gold, run the streaming pipeline, or use Lakebase.
Use the Bash tool's background caps generously; long downloads are expected.

**Commit your work** to `slice/bronze-fed` and write `.agents/<you>/VERDICT-bronze-fed.md`
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


# Lane 4: Federal Reserve/FRED

## Ownership

Only edit:

- `notebooks/refresh_bronze_fed.py`
- `tests/bronze/test_refresh_bronze_fed.py`

## Existing code to reuse

There is no existing Fed ingestion module or Bronze Fed table. Build this lane as a new self-contained notebook using:

- `requests`
- Python CSV parsing
- Spark explicit schemas
- append-only Delta writes
- serverless `DatabricksSession.builder.serverless(True)` when running outside a Databricks notebook, or the existing Spark session inside one

Do not put shared helpers into `etl/` in this four-builder change.

## Source and series list

Use the public no-key FRED CSV endpoint:

```text
https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES_ID>
```

Initial strategy-relevant series:

| Series | Meaning | Frequency |
|---|---|---|
| `DFF` | Effective federal funds rate | Daily |
| `DGS2` | 2-year Treasury constant maturity rate | Daily |
| `DGS10` | 10-year Treasury constant maturity rate | Daily |
| `T10Y2Y` | 10-year minus 2-year Treasury spread | Daily |
| `T10Y3M` | 10-year minus 3-month Treasury spread | Daily |
| `DFEDTARU` | Federal funds target range upper bound | Daily/changes |
| `DFEDTARL` | Federal funds target range lower bound | Daily/changes |
| `CPIAUCSL` | CPI, all urban consumers | Monthly |
| `CPILFESL` | Core CPI | Monthly |
| `UNRATE` | Unemployment rate | Monthly |
| `PAYEMS` | Total nonfarm payrolls | Monthly |
| `INDPRO` | Industrial production | Monthly |

Treat `"."`, empty strings, and non-numeric values as null/missing observations and do not emit value rows for them.

## New target table

Create `bootcamp_students.evangoh_capstone.bronze_fed_series` only if absent, using:

```text
series_id                STRING     NOT NULL
observation_date         DATE       NOT NULL
value                    DOUBLE     NOT NULL
vintage_date             DATE       NOT NULL
information_available_ts TIMESTAMP  NOT NULL
source                   STRING     NOT NULL
source_url                STRING     NOT NULL
ingest_ts                 TIMESTAMP  NOT NULL
raw_value                 STRING
revision_class            STRING     NOT NULL
```

Semantics:

- `observation_date`: period represented by the value.
- `value`: parsed published value.
- `vintage_date`: date this version was retrieved/published as a vintage.
- `information_available_ts`: earliest instant this stored version may be used in a point-in-time join. For `market_rate` series, this is the next NY business day after `observation_date` at 16:30 America/New_York (H.15 publication calendar). For `revised_macro` series, this equals `ingest_ts`.
- `source = 'fred_csv'`.
- `source_url`: exact series URL, without credentials or transient tokens.
- `ingest_ts`: UTC retrieval timestamp.
- `raw_value`: original CSV value.
- `revision_class`: `'market_rate'` for effectively unrevised daily rates (DFF, DGS2, DGS10, etc.) or `'revised_macro'` for monthly macro series revised after first release (CPIAUCSL, UNRATE, PAYEMS, etc.).

## Incremental window

The table does not yet exist, so the first run is a bounded bootstrap through **2026-10-03**.

Per series:

- If no rows exist, request the full CSV history supplied by FRED and retain observations through 2026-10-03.
- On later runs, request the CSV again and compare observations from `MAX(observation_date)` with an overlap appropriate to revisions:
  - Daily series: 14-day overlap.
  - Monthly series: 24-month overlap.
- New observation dates and changed values become candidate vintages.
- Unchanged values already stored for the same series, observation, value, and vintage must not be appended.

This overlap is necessary because monthly macro values may be revised and a strict `max date + 1` pull would miss them.

## Vintage and information-availability policy

Plain FRED CSV returns the latest revised history; it does not reconstruct what was known on each historical release date.

Therefore:

1. For the initial historical bootstrap, set:
   - `vintage_date = DATE(ingest_ts)`
   - `information_available_ts = ingest_ts`

   This is conservative and point-in-time safe: the backfilled values cannot be used as if they were historically known before ingestion.

2. For scheduled subsequent polling:
   - When a new observation or changed value is first seen, set `vintage_date = DATE(ingest_ts)`.
   - Set `information_available_ts = ingest_ts`.
   - Never backdate availability to `observation_date`.

3. A changed value is a new vintage and must be appended, not used to update the earlier value.

4. **ALFRED vintages are required** before these macro series can support a strict historical backtest with the values actually known at each past date. ALFRED integration is not part of this refresh because the measured accessible endpoint is FRED CSV. Until ALFRED is added, historical bootstrap rows are usable only from their ingestion timestamp onward.

This policy avoids inventing publication times for CPI, payrolls, unemployment, or revised rates.

## Idempotency

Natural version key:

```text
(series_id, observation_date, vintage_date, value)
```

Before append:

- `dropDuplicates` on the version key;
- left anti-join against the target on the same key.

For multiple runs on the same date, unchanged values will not duplicate. If a value changes again on the same date, the different `value` represents a distinct observed revision. `ingest_ts` and `information_available_ts` are metadata, not deduplication fields.

Tests must cover:

- `"."` handling;
- daily and monthly date parsing;
- unchanged overlap;
- changed values becoming new vintages;
- same-day rerun idempotency;
- `market_rate` availability at NY time (not `ingest_ts`);
- `revised_macro` availability equals `ingest_ts`.

## Dry-run and write sequence

1. Validate the fixed allow-list of series IDs.
2. Read existing per-series maxima and recent versions if the table exists.
3. Download each public CSV with bounded timeout and retry behavior.
4. Validate that the response has `DATE` plus the requested series column.
5. Parse through 2026-10-03, applying initial or overlap filtering.
6. Compare values to stored versions.
7. Print per-series source rows, missing values, unchanged rows, changed revisions, and new rows.
8. Dry-run performs no table creation or append.
9. Write mode creates the table if absent and appends only anti-joined rows.
10. A failure for one series must be reported by series ID; the run must not claim complete success.

## Verification

```sql
SELECT series_id,
       COUNT(*) AS rows,
       MAX(observation_date) AS max_observation_date,
       MAX(information_available_ts) AS max_available_ts
FROM bootcamp_students.evangoh_capstone.bronze_fed_series
GROUP BY series_id
ORDER BY series_id;
```

```sql
SELECT series_id, observation_date, vintage_date, value, COUNT(*) AS n
FROM bootcamp_students.evangoh_capstone.bronze_fed_series
GROUP BY series_id, observation_date, vintage_date, value
HAVING COUNT(*) > 1;
```

The duplicate query must return zero rows. Also verify:

```sql
SELECT COUNT(*) AS unsafe_rows
FROM bootcamp_students.evangoh_capstone.bronze_fed_series
WHERE (revision_class = 'revised_macro' AND information_available_ts < ingest_ts)
   OR observation_date > DATE '2026-10-03';
```

`unsafe_rows` must be zero, and post-count minus pre-count must equal the appended total.

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


# Coordinator amendment (Claude) — Fed availability policy by series type

Codex's policy above sets `information_available_ts = ingest_ts` for **all** bootstrapped FRED
history. That is right for revised macro series, but applied to every series it makes all Fed
features unusable for the 2022–2026 backtest. Split by revision behaviour:

| Class | Series (examples) | `information_available_ts` | Rationale |
| :-- | :-- | :-- | :-- |
| **Market rates** — effectively unrevised, published next business day | `DFF`, `DGS2`, `DGS10`, `T10Y2Y`, other H.15 daily rates | next New York business day after `observation_date`, 16:30 America/New_York (DST-aware) | H.15 daily rates are released the following business day; a conservative fixed time avoids look-ahead |
| **Revised macro** — revised after first release | `CPIAUCSL`, `UNRATE`, `PAYEMS`, GDP-type series | `ingest_ts` for bootstrapped history (Codex's rule); first-seen time for new vintages | Revised history must not be treated as historically known; needs ALFRED vintages for true PIT |

Store the class in a `revision_class` column (`market_rate` | `revised_macro`) so downstream code
and reviewers can see which rule applied. Everything else in Lane 4 stands, including
append-only new vintages and never backdating revised series.
