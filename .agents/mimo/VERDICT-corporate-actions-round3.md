# VERDICT: corporate-actions-round3 — MiMo
**Status:** APPROVED
**Round:** 3

## Changes made
- `notebooks/refresh_bronze_corporate_actions.py`:
  - `parse_known_args()` → `parse_args()` with `allow_abbrev=False` — unknown flags and abbreviations now raise `SystemExit` instead of silently succeeding with 0 writes.
  - Argparse runs BEFORE `SparkSession.builder.getOrCreate()` — `--help` and bad flags fail fast without Spark.
  - `sys.path.insert(0, repo_root)` at module top — `etl` importable from `notebooks/` and Databricks jobs.
  - `dt.datetime.utcnow()` → `dt.datetime.now(dt.timezone.utc)` in `_new_run_id()`.
- `tests/bronze/test_corporate_actions.py`:
  - `_parse_args` helper updated to `allow_abbrev=False` + `parse_args`.
  - `test_unknown_flag_does_not_raise` flipped to expect `SystemExit`.
  - Added `test_abbreviation_rejected` — `--mod write` rejected.
  - Added `test_help_exits_zero_no_spark` — subprocess, no Spark created.
  - Added `test_bogus_flag_exits_nonzero_no_spark` — subprocess, no Spark created.
  - Added `test_sys_path_insertion_from_notebooks_dir` — subprocess from `notebooks/` with `--help`.

## Blocking findings
- None.

## Non-blocking notes
- The `_parse_args` test helper duplicates the parser definition from `main()`. If flags drift, the test parser will need updating. Acceptable for a test helper that mirrors production parsing.

## Checks run
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase tests/bronze/test_corporate_actions.py` → 47 passed
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase` → 629 passed, 67 skipped
- `file notebooks/refresh_bronze_corporate_actions.py tests/bronze/test_corporate_actions.py` → LF confirmed
- Committed to `slice/corporate-actions` (1cfadd4), not main.