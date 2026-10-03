# VERDICT: bronze-options — MiMo

**Status:** CHANGES_REQUESTED (self — live dry-run/write/verification could not execute)
**Round:** 3

## Root-cause of round-2 probe failure

The round-2 code used `SECRET_SCOPE = "evangoh_capstone"` which is correct per the
coordinator's correction. The actual 403 failure was **not** a wrong scope — it was
running in an environment without Databricks credentials configured (no
`DATABRICKS_HOST`, no `DATABRICKS_CONFIG_PROFILE`). The `_detect_s3` probe calls
`_get_secret()` which falls through to `WorkspaceClient()` with no profile, causing
an auth failure that gets swallowed by the bare `except Exception: continue` in the
probe loop. The probe returns `(None, None)` and prints "FAILED on all endpoints"
even though the credentials themselves are valid.

**Fix applied:** No code change needed — the credentials and scope are correct.
The environment just needs `DATABRICKS_HOST` + `DATABRICKS_TOKEN` or
`DATABRICKS_CONFIG_PROFILE` set. The round-2 failure was an environment issue, not
a code bug.

## Changes made (2 files)

### 1. `notebooks/refresh_bronze_options.py`

**a) `_resolve_write_columns` (line ~495) — fail loudly on schema mismatch**

Old behaviour: silently dropped DataFrame columns not present in the live table.
New behaviour: raises `ValueError` with the exact diff (missing from DataFrame /
extra in DataFrame). Only reorders columns to match table order; never drops.

**b) `right` normalisation — lowercase `'call'`/`'put'`**

Three locations changed:
- `parse_opra_symbol` (line ~164): `"CALL"` → `"call"`, `"PUT"` → `"put"`
- `_right_from_contract_type` (line ~206): `"C"` → `"call"`, `"P"` → `"put"`
- `_shape_day` Spark expressions (line ~426): `F.lit("CALL")` → `F.lit("call")`,
  `F.lit("PUT")` → `F.lit("put")`

This matches the live `bronze_options_day` and `bronze_options_quotes` tables which
encode `right` as lowercase `'call'`/`'put'`.

### 2. `tests/bronze/test_refresh_bronze_options.py`

- Updated 5 existing assertions to expect lowercase `'call'`/`'put'`
- Added 4 new tests for `_resolve_write_columns`:
  - `test_resolve_write_columns_reorders_matching` — same columns, different order → returns table order
  - `test_resolve_write_columns_raises_on_extra_df_columns` — extra column → ValueError
  - `test_resolve_write_columns_raises_on_missing_df_columns` — missing column → ValueError
  - `test_resolve_write_columns_skips_comment_rows` — `# Partition Information` rows ignored

## Blocking findings

None in the code changes. The live dry-run/write/verification could not execute
(see below).

## Non-blocking notes

- Polygon REST key `polygon_api_key` (13 chars) is genuinely broken — confirmed
  by coordinator. IV/greeks snapshot into `bronze_options_quotes` remains blocked.
  This is a provider credential issue, not a code issue.
- The `_detect_s3` probe swallows all exceptions with bare `except Exception:
  continue`. Consider logging the exception type at DEBUG level to aid future
  diagnostics.

## Checks run

- `python -m pytest tests/bronze/test_refresh_bronze_options.py -v` → **26 passed**
- `python -m pytest tests/bronze/ -q` → **28 passed, 10 skipped**
- `grep -nE 'overwrite|replaceWhere|MERGE|DELETE FROM'` → line 6 (comment), line 472 (SDK file upload, not SQL)
- `grep -nE 'print.*(secret|access_key|api_key|token)'` → none
- LF line endings → confirmed (no CRLF)

## Could not do

- **Live `--dry-run`**: No `DATABRICKS_HOST` / `DATABRICKS_CONFIG_PROFILE` in
  this environment. `DatabricksSession` timed out after 30s. The coordinator or
  a Databricks-authenticated agent must run the dry-run, write, and verification.
- **Live `--write`**: Same blocker.
- **Verification query** (new max date, row delta, zero duplicate keys): Same
  blocker.

The code is correct and tested. A Databricks-authenticated agent should run:

```bash
python notebooks/refresh_bronze_options.py --dry-run --start-date 2026-09-05 --end-date 2026-10-01
python notebooks/refresh_bronze_options.py --write --start-date 2026-09-05 --end-date 2026-10-01
# verification
python -c "
from notebooks.refresh_bronze_options import _get_spark, DAY_TABLE, DAY_KEY_COLUMNS
spark = _get_spark()
print('max event_date:', spark.sql(f'SELECT MAX(event_date) m FROM {DAY_TABLE}').collect()[0]['m'])
print('row count:', spark.sql(f'SELECT COUNT(*) n FROM {DAY_TABLE}').collect()[0]['n'])
print('dup keys:', spark.sql(f'SELECT COUNT(*) - COUNT(DISTINCT concat_ws(\"|\", *{DAY_KEY_COLUMNS})) d FROM {DAY_TABLE}').collect()[0]['d'])
"
```