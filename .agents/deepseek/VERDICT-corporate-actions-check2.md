Checker: Claude Sonnet subagent (DeepSeek out of credit)

===VERDICT START===
# VERDICT: corporate-actions, round 2 re-check

**Status:** CHANGES_REQUESTED

## Blocking findings

1. [notebooks/refresh_bronze_corporate_actions.py:136-147; tests/bronze/test_corporate_actions.py:553-555]
   An unknown flag does NOT raise. `parser.parse_known_args()` silently discards it, and a test
   (`test_unknown_flag_does_not_raise`) asserts that behaviour. The re-check request requires that an
   unknown flag raises.
   Failure scenario: `--mdoe write` (typo) is ignored. The job runs in dry-run, appends zero Bronze
   rows and exits green. Proved: `parse_known_args(["--mod","write","--bogus"])` returned
   `Namespace(mode='write'), ['--bogus']`. Separately, `allow_abbrev` defaults to True, so `--mod`
   is accepted as `--mode`.
   Fix: use `parser.parse_args()` with `allow_abbrev=False`, and flip the test to expect `SystemExit`.
   If Databricks injects extra argv, whitelist those flags explicitly instead of ignoring everything.
   Bundle this with follow-up 2 below: parse args before creating Spark, so a bad flag fails fast.

## Non-blocking notes

Follow-ups from NOTES-claude-dryrun.md. None is fixed. Each is trivial and should go in the same round-3 patch as the blocking fix.
- (a) The `sys.path` insert of the repo root is absent. `grep sys.path` on the notebook is empty;
  `import sys` is present but unused for this. Running from `notebooks/` still hits
  `ModuleNotFoundError: etl` in `_make_adapter` (line ~63). Add
  `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))` at the top.
- (b) Argument parsing still runs after `SparkSession.builder.getOrCreate()` (spark at line 127,
  argparse at line 137). `--help` and bad flags need Spark first. I reproduced this: running
  `python notebooks/refresh_bronze_corporate_actions.py --bogus` locally died on the Spark
  session error before reaching argparse.
- (c) Line 49: `dt.datetime.utcnow()` is still used, which is deprecated. `_now_utc()` above it already
  does it correctly.
- `to_utc_timestamp(to_timestamp(string), tz)` depends on the Spark session timezone. It is correct
  when the session TZ is UTC (the Databricks default). Pinning `spark.sql.session.timeZone=UTC`
  would remove the dependency.
- The silver MERGE uses `UPDATE SET *` / `INSERT *`. I verified the source select lists all 24 target
  columns, the same names in the same order, so this is fine. It is not an explicit column list.
- A `;` sits after the section-10 header comment, so the section-9 MERGE is terminated oddly. Spark
  splits on `;`, so this is functional, but it is cosmetic debt.
- Carried over from round 1, unchanged and still non-blocking: the dedup partition is
  `(symbol, event_ts)`, not `event_date`; `matched_split_ratio` is stored as 1.0 rather than NULL
  when there is no split; and `run_silver_gold.py` registers the file twice.

## Checks run

Round-2 fixes:
- Item 1, DST pair (PASS). SQL line ~357 is
  `to_utc_timestamp(to_timestamp(concat(cast(event_date AS STRING),' 16:30:00')),'America/New_York')`.
  The direction is correct: NY wall time to UTC. The comment matches the code. Python zoneinfo
  proof: 2022-06-06 16:30 NY = 20:30 UTC; 2022-12-05 16:30 NY = 21:30 UTC. I could not run local
  Spark (pyspark here is Databricks-Connect only), so the Spark side is verified by reading the
  function semantics.
- Item 2, MERGE INSERT columns (PASS). Parsed from the SQL: `data_quality_breaks` target has 16
  columns, the INSERT list has 16 unique columns, the set equals the target, and the VALUES list has
  16 entries (reviewed_by and reviewed_ts are NULL). The silver MERGE uses `INSERT *`; its source
  select has all 24 target columns in order.
- Item 3, argparse (PARTIAL). `--mode write` gives mode "write" and the default is "dry-run" (code
  lines 150-160 plus tests). The unknown-flag requirement fails (blocking #1).

Round-1 re-checks (PASS, by code read plus the green tests):
- AMZN 20:1 gives about +2%, not -95%. `cumulative_split_ratio` counts splits with `ex_date > d`,
  and the factor is 1/ratio.
- Reverse and multiple splits are handled (log-sum-exp product). Volume is multiplied by the ratio,
  so it adjusts inversely.
- The adj_* levels are documented as returns-only, and PIT-safe `return_1d` is documented.
- The break detector uses |gross-1| >= 0.40, with a 3% split tolerance. META 2022-06-09 (no split) is
  UNEXPLAINED_PENDING and masked. `return_1d` is NULL when masked, never 0.
- Reviewed rows are preserved by `WHEN MATCHED AND reviewed_by IS NULL`; MERGE keys make reruns
  idempotent.
- The SQL references only the real `bronze_ohlcv_day` columns (symbol, event_ts, open, high, low,
  close, volume, vwap, trade_count, timespan, source, source_file, ingest_ts).

Test runs:
- `python3 -m pytest -q -p no:cacheprovider`: 2 failed, 679 passed, 67 skipped, 22 errors. All
  failures and errors are in tests/lakebase (they need live Postgres, which is pre-existing and
  unrelated).
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase`: 625 passed, 67 skipped.
- Repo read-only: `git status` was clean before my verdict file was written.
===VERDICT END===
