# VERDICT: xbrl-pr42-fixes-r2 — MiMo
**Status:** APPROVED
**Round:** 2

## Blocking findings
(none)

## Non-blocking notes
- Removed `TestBronzeSchemaContract` (7 tests) and `TestManifestSchemaContract` (8 tests) — all contracts now covered by plain-Python `TestBronzeColumnSpecContract` and `TestManifestColumnSpecContract`
- Restructured `TestFlattenedRowSchemaMatch` — removed PySpark skip, tests now use `BRONZE_COLUMNS`/`MANIFEST_COLUMNS` instead of `_get_*_schema()`
- Removed PySpark skip from `TestSparkWriterAppendMode` (5 tests) — uses `_mock_bronze_schema`/`_mock_manifest_schema` via `unittest.mock.patch`
- Removed PySpark skip from `TestCreateDataFrameAlwaysWithSchema` (3 tests) — same mock approach
- Removed PySpark skip from `TestEnsureTableIdempotent` (4 tests) — same mock approach
- Added `_MockFieldType`, `_MockField`, `_MockSchema` helpers to build mock schemas from `_ColumnSpec` lists
- Added `test_alter_missing_columns_derives_from_specs` to `TestManifestColumnSpecContract`
- Added `test_mutation_ddl_generator_drop_column_fails` to `TestManifestColumnSpecContract`
- Added `test_mutation_drop_column_from_specs_fails_contract` mutation test verified: dropping a column from `_columns_to_ddl` causes test failure without PySpark

## Checks run
- `python3 -m pytest tests/bronze/test_sec_companyfacts.py -v` → 91 passed (PySpark available)
- `python3 .agentlogs/test_blocked_pyspark4.py` (PySpark blocked via `find_spec`) → 91 passed, 0 skipped
- `python3 .agentlogs/count_skipped.py` → 0 PySpark-skipped tests (was 31, dropped by 31 ≥ 30)
- `python3 .agentlogs/test_mutation2.py` (drop value_decimal from DDL generator) → 1 failed, mutation detected