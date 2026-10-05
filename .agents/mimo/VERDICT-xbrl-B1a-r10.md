# VERDICT: xbrl-B1a-r10 — MiMo
**Status:** APPROVED
**Round:** 10

## Blocking findings
(none)

## Non-blocking notes
- The `_TYPE_MAP` dict is duplicated between `_schema_to_ddl_columns` and `ensure_table` ALTER path; could be extracted to a module-level constant in a future cleanup.
- The conftest `_block_network` guard allows loopback (127.0.0.1/::1/localhost) which is safe for bronze tests but worth noting if future tests need real localhost servers.

## Checks run
- `python3 -m pytest tests/bronze/test_sec_companyfacts.py -v --tb=short` → 88 passed in 1.12s
- `grep BRONZE_FACT_COLUMNS\|MANIFEST_COLUMNS pipelines/ingest_sec_companyfacts.py` → no matches (deleted)
- `git diff --stat` → 3 files changed, 90 insertions(+), 53 deletions(-)

## Changes made
1. **ALTER path derives from StructType** (`pipelines/ingest_sec_companyfacts.py`): `ensure_table` ALTER now iterates manifest schema fields, computes DDL type from `dataType.simpleString()`, and adds all missing columns in one statement. No hard-coded column names or types.
2. **Deleted dead column lists** (`pipelines/ingest_sec_companyfacts.py:176-219`): Removed `BRONZE_FACT_COLUMNS` and `MANIFEST_COLUMNS`. `_get_bronze_schema()` / `_get_manifest_schema()` + `_schema_to_ddl_columns()` are the single source of truth.
3. **Hermetic fallback test** (`tests/bronze/test_sec_companyfacts.py`): `test_fallback_when_volumes_not_writable` now passes `http_client=FakeHttpClient(...)` so no DNS/TCP occurs.
4. **Network guard in conftest** (`tests/bronze/conftest.py`): `_block_network` autouse fixture monkeypatches `socket.socket.connect` to raise `RuntimeError` on any non-loopback address, preventing future regressions.
5. **New test** (`tests/bronze/test_sec_companyfacts.py`): `test_ensure_table_alter_derives_two_missing_fields_from_schema` — simulates a table missing `error_category` and `error_message`, verifies exactly one ALTER adding both with `STRING` type from the StructType.