===VERDICT START===
# VERDICT: bronze-coderabbit — DeepSeek (independent checker)

**Status:** APPROVED
**Round:** 1
**Branch:** `slice/bronze-refresh`
**Commit reviewed:** `206bc5a` (MiMo, CodeRabbit round)

Checker verdict: read-only against the worktree. All scratch work happened under
`/tmp` (`/tmp/mutate.py`, `/tmp/muttest/`). Nothing was committed or pushed.

## Blocking findings

None.

## Answers to the five check questions (hardest first)

### 1. Fed dedup (`select_new_rows`, `_get_existing_keys`)

Verified correct. `_get_existing_keys`
(`notebooks/refresh_bronze_fed.py:365-398`) now returns `dict[(series_id,
observation_date) -> latest value]` (max `vintage_date` wins), and
`select_new_rows` (`:302-332`) appends only when the pair is absent **or** the
candidate `value` differs from the latest stored vintage. Confirmed each
sub-claim:

- **Same value on a later day → 0 new.** `test_next_day_same_value_not_appended`
  (`tests/bronze/test_refresh_bronze_fed.py:436`) passes.
- **Changed value → new vintage.** `test_next_day_changed_value_appended`
  (`:447`) passes.
- **A→B→A revert is new.** `test_value_revert_is_new_vintage` (`:458`) passes;
  the latest stored vintage is `B`, the candidate `A` differs, so it appends.
- **Still append-only.** The only write is
  `df.write.format("delta").mode("append").saveAsTable(fqn)` (`:430`). No
  UPDATE/DELETE/MERGE/OVERWRITE anywhere in the file.
- **Ties within the same vintage_date are NOT deterministic.** `:384` uses
  `vid >= latest[pair][0]` with no `ORDER BY` in the `collect()` at `:375-378`,
  so two rows sharing `(series_id, observation_date, vintage_date)` with
  different values break ties by Spark's arbitrary row order. This only arises
  on a same-day manual re-run that corrects a value, and even then the failure
  mode is a mis-dedup on a *future* run, never data loss. Non-blocking; a
  secondary sort on `ingest_ts` (not selected in the query today) would make it
  deterministic.
- **Float equality cannot re-parse an unchanged value as unequal.** `value` is
  `float(raw_string)` (`:179`) and is stored as `DOUBLE` (`:410`); the same CSV
  string round-trips bit-identically through `float → DOUBLE → float`, so
  `==` holds. A *different* string that parses to the same float (e.g. `"4.33"`
  vs `"4.330"`) is correctly treated as unchanged, which is the safe direction.
- **Claude's live dry-run (5 new, ~221 overlap, 0 dups).** Not independently
  reproducible here (requires a Databricks/Connect session against
  `bootcamp_students.evangoh_capstone.bronze_fed_series`). The 0-dups property
  is, however, exactly what `select_new_rows` guarantees on the overlap window,
  and the unit tests confirm the mechanism.

### 2. Every item 1-9: fixed or justified not-applicable

| # | Item | Result |
|---|---|---|
| 1 | Fed vintage-independent dedup | FIXED (`:302-332`, `:365-398`) |
| 2 | `dbutils.widgets.get` one-arg | FIXED (`refresh_bronze_equities.py:223-228`). Only equities uses widgets; fed/options/cot use argparse — grep confirms no remaining two-arg `widgets.get` |
| 3 | Options `expiry` as `date` | FIXED (`refresh_bronze_options.py:269-276`), `test_shape_quote_row_full` asserts `date(2026,12,18)` |
| 4 | Options `main` nonzero | FIXED (`refresh_bronze_options.py:957-959`) |
| 5 | `_stage_file` None → `log_finish(FAILED)` | FIXED (`:664-669`) |
| 6 | Fed `--start-date` bound / re-read COUNT / nonzero on mismatch | FIXED (`:490-497`, `:543-547`, `:574-576`) |
| 7 | `_anti_join_new` unit test | NOT-APPLICABLE — already present (`test_refresh_bronze_options.py:578-598`, three tests: dedup, exclude existing, pass new) |
| 8 | Class-specific availability docs | FIXED (`docs/BRONZE_REFRESH_PLAN.md` + `.agents/requests/BUILD-bronze-fed.md`; `revision_class` added to schema and semantics) |
| 9 | COT fallback offset explicit | FIXED (`docs/BRONZE_REFRESH_PLAN.md:375`, `refresh_bronze_cot.py:74`; code computes `3 + RELEASE_SAFETY_DAYS = 6` at `:156` and `:207`) |

`etl/extract_stocks.py` correctly left untouched (PR #13, out of scope).

### 3. H.15 availability calendar / point-in-time rules intact

Yes. The fix touched only `select_new_rows`/`_get_existing_keys` and the count
reporting; the calendar helpers (`_h15_holidays`, `_ny_available_ts`) and
`parse_csv_rows` availability logic are unchanged. The full fed test file (H.15
calendar, DST, `information_available_ts`, availability invariants) passes.

### 4. Exit codes: options/fed `main` return nonzero on partial failure

Yes, and the entrypoint propagates it.
- Options: `main` returns `1` when `daily is None` (S3 probe failed) or
  `daily["failed"] > 0` (`refresh_bronze_options.py:957-959`); `__main__` does
  `sys.exit(main(sys.argv[1:]))` (`:963`).
- Fed: `run_refresh` returns `1` on series failure or post/pre count mismatch
  (`refresh_bronze_fed.py:568-576`); `main` does `sys.exit(rc)` (`:600`).
- Non-blocking note: options still exits `0` when individual files are 403
  (`entitlement_gap > 0` but `failed == 0`), because 403 is classified as a
  gap, not `failed`. This matches the literal BUILD scope (`daily["failed"]>0`)
  but can mask a fully-empty-entitled window as success.

### 5. Do the new tests catch a vintage-dependent key regression?

Yes — proved by mutation under `/tmp`. I copied the fed module + test to
`/tmp/muttest/`, reverted `select_new_rows` to the pre-fix vintage-dependent key
(`(series_id, observation_date, vintage_date, value)`), and re-ran the suite:

```
$ PYTHONPATH=/tmp/muttest python3 -m pytest test_fed.py -q -k SelectNewRows --tb=line
F.FF....                                                              [100%]
FAILED test_fed.py::TestSelectNewRows::test_unchanged_overlap_excluded
FAILED test_fed.py::TestSelectNewRows::test_same_day_rerun_idempotency
FAILED test_fed.py::TestSelectNewRows::test_next_day_same_value_not_appended
3 failed, 5 passed
```

The regression-specific test `test_next_day_same_value_not_appended` fails
(`assert 1 == 0`), proving the tests catch a revert to a vintage-dependent key.

## Non-blocking notes

- `_get_existing_keys` `.collect()`s the full key/value set to the driver
  (`refresh_bronze_fed.py:375-378`). Fine at Bronze scale, but not the Spark
  left-anti-join the BUILD spec mentions; a performance-lane (MiMo) concern, not
  a correctness defect.
- Same-day-tie non-determinism in `latest` selection (see Q1).
- Options `entitlement_gap > 0` with `failed == 0` still exits `0` (see Q4).

## Checks run

```
$ python3 -m pytest tests/bronze -q
167 passed, 10 skipped in 20.72s
```

```
$ python3 -m pytest tests/bronze/test_refresh_bronze_fed.py tests/bronze/test_refresh_bronze_options.py -q
... all pass (subset of the 167 above)
```

```
$ grep -rn 'widgets.get(' notebooks/          # no two-arg .get(x, default) remains
$ grep -rn 'select_new_rows\|_get_existing_keys' notebooks tests   # callers consistent with new signatures
```
===VERDICT END===
