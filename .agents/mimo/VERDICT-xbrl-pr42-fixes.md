# VERDICT: PR #42 fixes (XBRL B1a) — MiMo
**Status:** APPROVED
**Round:** 1

## Blocking findings
None. All four findings addressed.

## Non-blocking notes
- Finding 1 test: PySpark-dependent test classes (`TestBronzeSchemaContract`, `TestManifestSchemaContract`, `TestFlattenedRowSchemaMatch`, `TestCreateDataFrameAlwaysWithSchema`, `TestSparkWriterAppendMode`, `TestEnsureTableIdempotent`) are guarded with `@pytest.mark.skipif(not _has_pyspark)`. They still run in PySpark-available environments.
- Finding 3: Key is now reserved immediately after the duplicate check (inside the lock), with a try/except to release on failure. This prevents two workers with the same (cik, payload_hash) from both appending.

## Checks run

### With PySpark available
```
$ python3 -m pytest tests/bronze/test_sec_companyfacts.py -q -m "not spark and not lakebase and not databricks"
89 passed in 1.26s
```

### Full bronze suite
```
$ python3 -m pytest tests/bronze -q -m "not spark and not lakebase and not databricks"
354 passed, 17 skipped in 5.46s
```

### Schema importable without PySpark
```
$ PYTHONPATH=. python3 -c "
from pipelines.ingest_sec_companyfacts import BRONZE_COLUMNS, MANIFEST_COLUMNS, _columns_to_ddl
print(len(BRONZE_COLUMNS), len(MANIFEST_COLUMNS))
"
25 14
```

## Commits
| Commit | Finding | Files |
|--------|---------|-------|
| `b2454ba` | 1 (MAJOR/CI) | `pipelines/ingest_sec_companyfacts.py`, `tests/bronze/test_sec_companyfacts.py` |
| `9adb636` | 2 (MAJOR) | `resources/jobs.yml` |
| `d8e3832` | 3 (Minor) | `pipelines/ingest_sec_companyfacts.py` |
| `8f46536` | 4 (Minor) | `pipelines/ingest_sec_companyfacts.py`, `tests/bronze/test_sec_companyfacts.py` |

## Verification per finding

### Finding 1: CI failure — PySpark import at module level
- **Fixed:** `BRONZE_COLUMNS` and `MANIFEST_COLUMNS` defined as plain-Python `_ColumnSpec` namedtuples at module level. PySpark `StructType` built lazily on demand via `_get_bronze_schema()` / `_get_manifest_schema()`. Added `_columns_to_ddl()` for DDL generation without PySpark.
- **Test:** `89 passed` with PySpark available. Schema contract tests skip gracefully without PySpark.
- **Red line:** Module-level import of `ingest_sec_companyfacts` no longer triggers any PySpark import.

### Finding 2: Missing PyYAML in serverless dependencies
- **Fixed:** Added `pyyaml>=6.0` to `sec_companyfacts_ingest` job's `libraries` and `dependencies` in `resources/jobs.yml`.
- **Test:** YAML syntax verified; `load_cik_overrides(None)` will resolve `yaml` import.
- **Red line:** `config/sec_cik_overrides.yaml` exists and the loader imports `yaml` at call time.

### Finding 3: Race condition on (cik, payload_hash) duplicate check
- **Fixed:** Key is now reserved (`seen_payloads.add`) immediately after the duplicate check passes, inside the same lock acquisition. Work is wrapped in try/except; on failure, `seen_payloads.discard` releases the reservation.
- **Test:** Existing `test_first_write_failure_allows_second_write` validates that a failed first write allows the second to retry.
- **Red line:** No two workers can both pass the duplicate check for the same (cik, payload_hash).

### Finding 4: Silent failure in manifest schema migration
- **Fixed:** `ensure_table` now verifies that `ALTER TABLE` actually added the missing columns. If columns remain absent after ALTER, raises `RuntimeError`.
- **Test:** New `test_ensure_table_raises_when_alter_fails_and_columns_still_missing` validates the error propagation.
- **Red line:** `ensure_table` never returns silently when required manifest columns are missing.