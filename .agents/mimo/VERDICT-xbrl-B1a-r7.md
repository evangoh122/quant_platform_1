# VERDICT: xbrl-B1a round 7 — MiMo
**Status:** APPROVED
**Round:** 7

## Blocking findings
None.

## Non-blocking notes
- All 4 items from BUILD-xbrl-B1a-r7.md implemented and tested.

## Changes made

### 1. Bronze StructType (item 1)
- `pipelines/ingest_sec_companyfacts.py`: Added `_get_bronze_schema()` lazy builder returning a 25-field `StructType` matching the DDL exactly (ingest_run_id STRING NOT NULL through source_updated_at STRING).
- Added `_coerce_bronze_row()` helper that coerces `fiscal_year` to `int|None` and uses `.get()` for all optional fields.
- `SparkCompanyFactsWriter.append_rows()` now passes `schema=bronze_schema` to `createDataFrame` — no inference.

### 2. Manifest StructType + http_status (item 2)
- `pipelines/ingest_sec_companyfacts.py`: Added `_get_manifest_schema()` lazy builder returning a 14-field `StructType` matching the DDL (includes `http_status INT`).
- `SparkCompanyFactsManifestWriter.ensure_table()` now runs `ALTER TABLE … ADD COLUMNS (http_status INT)` idempotently after CREATE TABLE IF NOT EXISTS.
- `SparkCompanyFactsManifestWriter.write_manifest()` now passes `schema=manifest_schema` to `createDataFrame`.

### 3. Tests (item 3)
- `tests/bronze/test_sec_companyfacts.py`: Added 5 new test classes (17 test methods):
  - `TestBronzeSchemaContract`: field count (25), names match DDL order, types match, mutation-proof.
  - `TestManifestSchemaContract`: field count (14), names match DDL order, types match, http_status present, mutation-proof.
  - `TestFlattenedRowSchemaMatch`: coerced row has all keys, fiscal_year int coercion, manifest entry dict matches schema.
  - `TestCreateDataFrameAlwaysWithSchema`: spy verifies schema= kwarg on both writers, mutation-proof (remove schema → test fails).
  - `TestCachePathFallback`: /Volumes not writable → falls back to tempdir.

### 4. Cache path fallback (item 4)
- `pipelines/ingest_sec_companyfacts.py`: When `cache_path` is auto-generated (None → default /Volumes path), checks `os.access()` on the parent directory. If not writable, falls back to `tempfile.gettempdir()/sec_cache/company_tickers.json` with a warning log.

## Checks run
```
python3 -m pytest tests/bronze/test_sec_companyfacts.py -v --tb=short → 75 passed in 1.08s
```

## Files modified
- `pipelines/ingest_sec_companyfacts.py` (+120 lines)
- `tests/bronze/test_sec_companyfacts.py` (+280 lines)