===VERDICT START===
# VERDICT: corporate-actions — DeepSeek (schema / SQL / API-contract lane)

**Status:** CHANGES_REQUESTED
**Round:** 1
**Branch:** `slice/corporate-actions` (`82ac927..HEAD`, plus `origin/main` base)

Checker verdict: I read and ran the code/tests but did not modify the worktree
(working tree is clean). Scratch work under `/tmp` (`/tmp/verify_ca.py`,
`/tmp/nopyspark/`). No network calls in tests — verified by reading all test
modules (they import only fakes/pandas fixtures) and by running the focused
suite with pyspark import-blocked.

## Blocking findings

1. **[silver/08_silver_ohlcv_day_adjusted.sql:338-341] Daily `information_available_ts`
   is wrong in both time and timezone direction.**
   The code computes
   `from_utc_timestamp(to_timestamp(concat(cast(event_date AS STRING),' 16:00:00')), 'America/New_York')`.
   `from_utc_timestamp` interprets its input **as UTC** and returns a NY-local
   wall time, so `'2022-06-06 16:00:00'` becomes `12:00` ET (EDT), stored naive.
   Two defects: (a) it uses `16:00`, not the required `16:30`; (b) it converts in
   the wrong direction — the spec (BUILD §4) and `docs/DATA_SCHEMAS.md` require
   "16:30 America/New_York converted to UTC" (i.e. `20:30 UTC` on 2022-06-06).
   The comment on line 337 even says "16:30 ET", contradicting the code.
   → Failure scenario: the daily bar's availability stamp is ~4.5h early and
   timezone-inverted; any downstream PIT/availability gate keyed on this column
   will admit a daily return before its 16:30 ET close. (Note the bronze
   `information_available_ts` at 09:30 ET — `etl/corporate_actions.py:69-83` — is
   correct; only this daily one is wrong.)
   Fix: `to_utc_timestamp(to_timestamp(concat(cast(event_date AS STRING),' 16:30:00')), 'America/New_York')`.

2. **[silver/08_silver_ohlcv_day_adjusted.sql:296] `data_quality_breaks` MERGE
   `WHEN NOT MATCHED THEN INSERT *` has a 14-column source but a 16-column target.**
   Target (`:24-42`) declares `reviewed_by`, `reviewed_ts` (positions 13–14) that
   the source subquery (`:265-281`) does not select; `detected_ts`/`processed_ts`
   therefore sit at source positions 13–14 but target positions 15–16. Databricks
   `INSERT *` is documented to require "the source table has the same columns as
   those in the target table", and every other MERGE in this repo (e.g.
   `silver/01_silver_ohlcv.sql:22-78`, `silver/04_silver_options_trades.sql:13-43`)
   keeps source and target column sets identical.
   → Failure scenario: the `data_quality_breaks` MERGE throws an analysis error
   at build time (or, if resolved positionally, silently writes
   `detected_ts`/`processed_ts` into `reviewed_by`/`reviewed_ts`), so the
   first-ever Silver build cannot populate the break table.
   Fix: add `NULL AS reviewed_by, NULL AS reviewed_ts` to the source (and align
   `detected_ts`/`processed_ts`), or use an explicit `INSERT (col,…) VALUES (…)`
   list.

3. **[notebooks/refresh_bronze_corporate_actions.py:135-176] Ingest parameters are
   read only via `dbutils.widgets.get()`; there is no `argparse`/`sys.argv`
   parsing.** `resources/jobs.yml:22-30` passes `--mode`, `--delay-seconds` as
   `spark_python_task.parameters` (which become `sys.argv`), and
   `docs/CORPORATE_ACTIONS_RUNBOOK.md:42-81` invokes
   `python notebooks/refresh_bronze_corporate_actions.py --mode write --run-id …`.
   None of these flags are ever consumed; the module-level grep for
   `argparse|sys.argv` is empty.
   → Failure scenario: the runbook "Fetch/write" step (`--mode write`) silently
   runs in the default `dry-run` mode and appends **zero** Bronze rows, and
   resume/sharding (`--run-id`, `--symbol-start`, `--symbol-end`) can never be
   supplied externally, so the CHECK item 5 requirements (rate-limited,
   resumable, dry-run/write) are not reachable through the documented interface.
   Fix: add `argparse` handling in `main()` (or make `resources/jobs.yml` a
   `notebook_task` with widget parameters) and keep the `dbutils.widgets` path
   for interactive use.

## Non-blocking notes

- [silver/08_silver_ohlcv_day_adjusted.sql:95-98] Dedup `ROW_NUMBER` partitions on
  `(symbol, event_ts)`, but BUILD §4 requires `(symbol, event_date)`, and the code
  derives `event_date` via `DATE(event_ts)` rather than using the native
  `bronze_ohlcv_day.event_date` column. If two source rows for one day carry
  different `event_ts`, both survive (`rn=1` each) and the final
  `(symbol,event_date)` MERGE key can duplicate/error. Correct today only because
  the daily provider stamps a single time-of-day.
- [etl/corporate_actions.py:126] `self._delay` is stored but never used — rate
  limiting actually lives in the notebook loop (`_time.sleep(delay_seconds)` at
  `notebooks/refresh_bronze_corporate_actions.py:333`), and the retry backoff
  base is hardcoded (`2**attempt*0.5`, `:200`) rather than the injected delay.
- [silver/08_silver_ohlcv_day_adjusted.sql:208] `matched_split_ratio` is stored as
  `COALESCE(day_split_ratio, 1.0)`, i.e. `1.0` (not `NULL`) for non-split
  candidates; `day_split_ratio != 1.0` is used as a "has a split" sentinel. Spec
  marks this column "same-day product, **if any**" (nullable) — minor semantics
  drift, not a correctness break.
- [pipelines/run_silver_gold.py:50-51] The same
  `silver/08_silver_ohlcv_day_adjusted.sql` file is registered twice (once as
  `silver_ohlcv_day_adjusted`, once as `data_quality_breaks`), so both `MERGE`s
  execute twice per build. Idempotent (CREATE IF NOT EXISTS + MERGE), but wasteful;
  the second `count()` is redundant.
- [etl/corporate_actions.py:165-207] A "not found" symbol whose `ticker.history()`
  raises is retried (outer `except`), whereas empty-history is correctly
  non-retried; minor deviation from "no retry for permanent not-found".

## Answers to the six check questions

1. **Adjustment arithmetic — PASS (verified by hand + tests).**
   AMZN 20:1 (ex 2022-06-06): `cumulative_split_ratio(06-03)=20`, factor `1/20`,
   `adj_prev=2447/20=122.35`, `adj_ex=124.79`, return `124.79/122.35-1 = +1.99%`
   (not −95%). Reverse 1:10 (`ratio=0.1`): prior price ×10, prior volume ×0.1.
   Multiple splits compound via `EXP(SUM(LN(ratio)))` (log-sum-exp). Dollar volume
   invariant: `adj_close·adj_volume = (close/r)·(vol·r) = close·vol` (verified
   numerically in `/tmp/verify_ca.py`). Tests `tests/silver/test_ohlcv_day_adjusted.py`
   cover forward/reverse/multiple/no-split + tight split-day-truth tolerance.

2. **PIT — PASS.** `adj_*` are documented global/current-scale display levels
   ("returns-only", `docs/DATA_SCHEMAS.md` silver block; `:11-15` of the SQL). The
   PIT helper (`pit_factor = 1/PRODUCT(ratio where row_date<ex_date AND
   information_available_ts<=t)`) is implemented and tested in
   `tests/silver/test_ohlcv_day_adjusted.py::TestPITAdjustment` (future split changes
   global but not PIT; availability boundary respected). Bronze
   `information_available_ts` = 09:30 NY on ex-date, DST-correct (13:30/14:30 UTC
   EDT/EST — verified). Canonical `return_1d` is PIT-safe as documented. **Caveat:**
   the *daily* `information_available_ts` (16:30) is broken — see blocking #1.

3. **Break detector — PASS.** Candidate = `abs(close/prev_close−1) ≥ 0.40`; explained
   only if a same-date split exists and `abs((close/prev)·ratio−1) ≤ 0.03`; otherwise
   `UNEXPLAINED_PENDING` (masked fail-closed). Masked `return_1d` is `NULL`, never 0
   (`:327-331`). `ALLOW_REAL_MOVE`/`CONFIRMED_DATA_BREAK` reviews persist via
   `WHEN MATCHED AND tgt.reviewed_by IS NULL` (`:284`). Every mask is a row in
   `data_quality_breaks` (reviewable). META 2022-06-09 (no split) → PENDING; AMZN →
   SPLIT_EXPLAINED (unmasked). Conservative (3% absolute tolerance, not ≥40%
   auto-delete). **Caveat:** the review-preserving MERGE's insert path is broken —
   see blocking #2.

4. **Idempotency — PASS in design.** Bronze is append-only
   (`mode("append")`, `:370`), key `(symbol,ex_date,source)` excluding `fetched_ts`
   (`:36`), in-batch dedup + driver-side anti-join + conflict reporting (`:307-339`).
   Silver MERGEs on `(symbol,event_date)` and re-adjusts on new splits. Rerun with
   identical inputs yields identical output / zero new rows (tested).

5. **Ingestion — PARTIAL.** Dry-run/rate-limit/retry/resume/conflict logic is
   present and correct; tests are offline (no yfinance import at test time — only
   fixtures; `TestImportSafety` asserts no side effects). **But** the external
   parameter surface is non-functional (blocking #3): `--mode write`, `--run-id`,
   bounds, and delay are not parsed, so write/resume cannot be triggered via the
   runbook or the job.

6. **SQL column references — PASS.** Only real `bronze_ohlcv_day` columns are
   referenced (`symbol, event_ts, open, high, low, close, volume, vwap, trade_count,
   timespan, source, source_file, ingest_ts`); `DATE(event_ts)` is used instead of the
   native `event_date` (non-blocking #1 above), but no fabricated columns appear.

## Checks run

```
$ python3 -m pytest -q -p no:cacheprovider tests/bronze/test_corporate_actions.py tests/silver/test_ohlcv_day_adjusted.py
74 passed in 0.54s

$ PYTHONPATH=/tmp/nopyspark python3 -m pytest -q -p no:cacheprovider tests/bronze/test_corporate_actions.py tests/silver/test_ohlcv_day_adjusted.py
74 passed in 0.63s            # pyspark import-blocked — proves no pyspark/network needed

$ python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase
612 passed, 67 skipped in 103.35s

$ PYTHONPATH=/tmp/nopyspark python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase
602 passed, 77 skipped in 95.70s   # 10 pyspark-dependent tests correctly skip

$ python3 -m pytest -q -p no:cacheprovider                     # full suite incl. lakebase
2 failed, 666 passed, 67 skipped, 22 errors   # failures/errors all in tests/lakebase (live Postgres)

$ git diff --check && git status --porcelain
(clean; no whitespace errors, working tree clean)
```

The 2 lakebase failures/errors are pre-existing live-DB tests unrelated to this
lane; with `--ignore=tests/lakebase` the suite is fully green.

The three blocking findings are SQL/plumbing defects not exercised by the offline
tests (the SQL contract tests only assert column *names* appear, not the
`information_available_ts` expression, and no test parses the notebook's argv or
executes the `data_quality_breaks` MERGE against Delta). They must be fixed before
this lane is APPROVED.
===VERDICT END===
