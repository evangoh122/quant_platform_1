# VERDICT: xbrl-B1a-r9 — MiMo
**Status:** APPROVED
**Round:** 9

## What changed

- `pipelines/ingest_sec_companyfacts.py`: Added `_schema_to_ddl_columns(schema)` helper that generates a DDL column list from a StructType using `field.dataType.simpleString()` and `NOT NULL` where `nullable=False`. Updated both `SparkCompanyFactsWriter.ensure_table` and `SparkCompanyFactsManifestWriter.ensure_table` to generate DDL from the StructType instead of hand-written column lists.

- `tests/bronze/test_sec_companyfacts.py`: Added `_parse_ddl_columns()` helper and 6 new tests:
  - `test_bronze_generated_ddl_matches_struct_type` — round-trip: StructType → DDL → parse → compare
  - `test_bronze_ddl_column_names_match_hardcoded_list` — generated DDL matches hardcoded reference
  - `test_mutation_drop_field_from_bronze_struct_fails_contract` — dropping a field fails the contract
  - `test_manifest_generated_ddl_matches_struct_type` — round-trip for manifest
  - `test_manifest_ddl_column_names_match_hardcoded_list` — generated DDL matches hardcoded reference
  - `test_mutation_drop_field_from_manifest_struct_fails_contract` — dropping http_status fails the contract

## Blocking findings

None.

## DeepSeek r7+r8 blocking findings addressed

1. **DDL and StructType were independent hardcoded column lists** → FIXED: DDL is now generated from the StructType via `_schema_to_ddl_columns()`. They cannot drift apart.

2. **Removing `http_status` from manifest DDL alone did not fail any test** → FIXED: The DDL is no longer a separate string. It is derived from the StructType. The mutation tests (`test_mutation_drop_field_from_*_struct_fails_contract`) prove that dropping a field from the StructType causes the contract test to fail. The DDL cannot be edited independently.

## Specific mutations requested (r9)

1. **Drop a field from the StructType → contract test fails** → VERIFIED: `test_mutation_drop_field_from_bronze_struct_fails_contract` and `test_mutation_drop_field_from_manifest_struct_fails_contract` both demonstrate this. The generated DDL has fewer columns than the full schema, and the round-trip comparison catches the mismatch.

2. **DDL can no longer drift separately** → VERIFIED: Since the DDL is generated from the StructType at runtime, there is no separate DDL string to edit. The single source of truth is the StructType.

## Non-blocking notes

- `MANIFEST_COLUMNS` (line 174) and `BRONZE_FACT_COLUMNS` (line 145) are now dead code — they were the old hand-written column lists. Recommend deleting them in a future cleanup.
- The ALTER-missing-columns logic in `SparkCompanyFactsManifestWriter.ensure_table` is still driven by the column list (checking `http_status` existence), which is correct — it handles the legacy table migration case.

## Checks run

- `python3 -m pytest tests/bronze/test_sec_companyfacts.py -q` → **87 passed** (81 existing + 6 new)
- `python3 -m pytest tests/rag/test_sec_rag_ingest.py -q` → **203 passed**
- Total → **290 passed** (baseline was 284, +6 new contract tests)
- Working tree: clean, committed as `acf0ede` on `feat/xbrl-fundamentals`