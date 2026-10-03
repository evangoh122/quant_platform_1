# VERDICT: bronze-cot — MiMo

**Status:** APPROVED
**Round:** 2

## Blocking findings

(none)

## Non-blocking notes

- The `CREATE TABLE IF NOT EXISTS` DDL uses `simpleString()` for column types, which maps PySpark `StringType` → `string`, `IntegerType` → `int`, etc. These are valid Delta SQL types. If a future schema uses nested types (array/map/struct), the DDL generation would need a more robust `sql()` formatter — but the current TFF Bronze schema is all-StringType, so this is safe today.
- The duplicate-key verification (`groupBy().count().filter(count > 1).count()`) adds one extra scan of the target table after write. For the current ~600-row tables this is negligible; for larger tables consider sampling or a `MERGE INTO` approach instead.
- `anti_join_new_rows` does a `.distinct()` on the full target key set. For very large targets this is an O(n) shuffle. Fine at current scale; would need broadcast-join or bloom filter at >10M rows.

## Checks run

- `python3 -m pytest tests/bronze/test_refresh_bronze_cot.py -q` → `36 passed in 24.06s`
- `python3 notebooks/refresh_bronze_cot.py --dry-run` → 0 new rows for both com_fin and fut_fin (tables current to 2026-09-22)
- `file notebooks/refresh_bronze_cot.py tests/bronze/test_refresh_bronze_cot.py` → both `UTF-8 text executable` (no CRLF)
- `git diff --stat` → `2 files changed, 199 insertions(+), 73 deletions(-)`
- Committed as `68c62bc` on `slice/bronze-cot`

## Fixes applied

1. **Never overwrite** — `refresh_bronze_cot.py:458-465`: replaced `.mode("overwrite").saveAsTable()` with `CREATE TABLE IF NOT EXISTS (...) USING DELTA` DDL + `.mode("append")`.
2. **Verify before success** — `refresh_bronze_cot.py:467-497`: after each append, asserts `post_count - pre_count == new_count` and checks zero duplicate keys in target. Sets `status = FAILED` + nonzero error on mismatch.
3. **Off-by-one** — `refresh_bronze_cot.py:407`: changed `> start_date` to `>= start_date`. A report exactly one day after `max(report_date)` is no longer skipped.
4. **Tests call production code** — `test_refresh_bronze_cot.py`: replaced tautological `TestValidateContractCodeColumn`, `TestNaturalKey`, and `TestIdempotency` tests with tests that call `validate_contract_code_column`, `anti_join_new_rows`, `detect_revision_conflicts`, and `to_bronze` directly. Added `spark` fixture (Databricks Connect with local fallback). Updated `TestIncrementalWindow` to match `>=` semantics.