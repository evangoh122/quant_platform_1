# BUILD-REQUEST: bronze-refresh — lane `cot`

**Branch:** `slice/bronze-cot` (its own worktree, off `slice/bronze-refresh`).
Full plan: `docs/BRONZE_REFRESH_PLAN.md` (written by Codex). Your lane is below, verbatim.
Three other builders run the other lanes **concurrently**. Edit **only** your lane's
exclusive files listed under "File ownership". Do not touch shared files.

**Execution:** this lane writes to live bronze tables. Run `--dry-run` first and paste its
report; then `--write`; then the verification queries. Bronze is **append-only** (a streaming
pipeline reads `bronze_ohlcv` as a stream): no UPDATE/DELETE/MERGE-update/overwrite, ever.
Never print secret values. Do not rebuild silver/gold, run the streaming pipeline, or use Lakebase.
Use the Bash tool's background caps generously; long downloads are expected.

**Commit your work** to `slice/bronze-cot` and write `.agents/<you>/VERDICT-bronze-cot.md`
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


# Lane 3: CFTC COT

## Ownership

Only edit:

- `notebooks/refresh_bronze_cot.py`
- `tests/bronze/test_refresh_bronze_cot.py`

## Existing code to reuse

Copy and adapt the CFTC TFF implementation from `notebooks/archive/00_project_setup.py`:

- `cftc_url`
- `download_year`
- `sanitize_columns`
- `to_bronze`
- the separate `com_fin` and `fut_fin` datasets
- raw string preservation
- typed `report_date`, `report_year`, `release_ts`
- lineage fields `source_dataset`, `source_file`, `ingest_ts`

Do not reuse its `write_year` overwrite/`replaceWhere` operation.

`etl/extract_cot.py` may be used only as a reference for the public Socrata endpoint and market mapping. Do not call `run_cot_etl`, because it uses the retired DuckDB writer and ingests Legacy reports rather than the established TFF schemas.

## Sources and targets

| Dataset | Source | Target |
|---|---|---|
| TFF futures and options combined | CFTC `com_fin_txt_2026.zip` or equivalent PRE records | `bootcamp_students.evangoh_capstone.bronze_cftc_com` |
| TFF futures only | CFTC `fut_fin_txt_2026.zip` or equivalent PRE records | `bootcamp_students.evangoh_capstone.bronze_cftc_fut` |

Keep the two classifications separate. Preserve all CFTC source columns as strings and append:

- `report_date DATE`
- `report_year INT`
- `release_ts TIMESTAMP`
- `source_dataset STRING`
- `source_file STRING`
- `ingest_ts TIMESTAMP`

## Incremental window

Both tables currently end at report date **2026-09-01**.

Fetch/filter reports where:

```text
report_date > 2026-09-01
report_date <= 2026-10-03
```

At runtime derive the lower bound independently from `MAX(report_date)` in each table. Querying the current annual file is acceptable, but filter and append only reports after the table maximum. A report dated after the run date must be rejected.

COT is normally a Tuesday position report released later. A table may legitimately remain behind the current date if the next report has not been published.

## Release and availability time

Continue to expose `release_ts`; never use `report_date` as the information-availability time.

The archived nominal rule is Friday at 15:30 America/New_York, derived as report date plus three days. Holiday weeks can publish later. For this refresh:

- Prefer an official publication/release timestamp present in the PRE record.
- Otherwise set the conservative fallback to the following Monday at 15:30 America/New_York by using `RELEASE_SAFETY_DAYS = 3`.
- Preserve the timestamp in UTC.

This sacrifices some Friday-to-Monday availability but avoids holiday-week lookahead. A later Silver step may replace the fallback with an official release calendar; that work is out of scope here.

## Idempotency

CFTC source schemas can contain multiple rows per market/report because of contract identifiers or submarket distinctions. Use the source’s stable CFTC contract market code rather than display name.

Natural key for each target:

```text
(source_dataset, cftc_contract_market_code, report_date)
```

Use the actual sanitized contract-code column present in the live table/source, typically `CFTC_Contract_Market_Code`. Fail dry-run if no stable contract-code column can be identified; do not fall back silently to row position.

Apply incoming `dropDuplicates` and a target left anti-join on that key before append.

Because the key admits one record per report/contract/dataset, later revisions to an already-ingested report will not overwrite history or silently replace it. Report revised values detected for an existing key as a revision conflict. Capturing full CFTC revision history would require an explicit vintage key and is outside this refresh.

## Dry-run and write sequence

1. Read each target’s count, maximum report date, and actual column set.
2. Download only the current 2026 annual source artifacts, or request the equivalent incremental PRE rows.
3. Preserve raw strings and apply the existing minimal derived columns.
4. Filter separately using each table’s maximum `report_date`.
5. Validate non-null report date, contract code, expected year, and release timestamp.
6. Detect existing-key/value conflicts and report them separately from exact duplicates.
7. Deduplicate and anti-join.
8. Dry-run prints candidate/new/conflict counts.
9. Write mode appends only new keys.
10. A failure in `com_fin` must not mark `fut_fin` successful, or vice versa.

## Verification

For both tables:

```sql
SELECT COUNT(*) AS rows,
       MAX(report_date) AS max_report_date,
       MAX(release_ts) AS max_release_ts
FROM bootcamp_students.evangoh_capstone.<target>;
```

```sql
SELECT source_dataset,
       CFTC_Contract_Market_Code,
       report_date,
       COUNT(*) AS n
FROM bootcamp_students.evangoh_capstone.<target>
WHERE report_date > DATE '2026-09-01'
GROUP BY source_dataset, CFTC_Contract_Market_Code, report_date
HAVING COUNT(*) > 1;
```

Adapt only the capitalization of the contract-code column to the actual sanitized schema. Duplicate checks must return zero rows. Also verify:

- `release_ts > report_date`;
- post-count minus pre-count equals appended count;
- `com_fin` rows never enter `bronze_cftc_fut` and vice versa;
- no future report dates were written.

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


