# VERDICT: rag-kg-round3 — MiMo
**Status:** APPROVED
**Round:** 3

## Blocking findings addressed

### 1. False chunk-level citations (`sec_kg/build.py`)
- **Fixed:** Removed the arbitrary `sorted(chunks)[0]` fallback that assigned chunk-level citations without verifying the chunk contained the fact.
- **Implemented:** Conservative matcher (`_chunk_text_matches_value`) that verifies chunk text contains the entity value in normalised form (e.g., 274300000 ↔ "274,300,000") AND the period or metric label.
- **Result:** All 43,722 XbrlFact nodes now have `citation_level=filing` (previously 5,118 had false chunk-level citations). SOURCED_FROM edges dropped from 6,575 to 1,457 (only RiskFactor nodes with matching chunk text).
- **Tests added:** `test_chunk_text_contains_value_gets_chunk_level`, `test_arbitrary_same_filing_chunk_without_value_filing_level`.

### 2. SparkGraphStore provenance column mismatch (`api/services/sec_knowledge_graph.py:168-236`)
- **Fixed:** Reader now accesses `row.provenance` (ARRAY<STRUCT>) instead of `row.provenance_json` (non-existent column). Removed `json.loads()` since the data is already structured.
- **Writer schema:** `provenance ARRAY<STRUCT<accession_number:STRING,source_chunk_id:STRING,accepted_ts:TIMESTAMP>>` (pipelines/build_sec_knowledge_graph.py:97-101,108).
- **Tests added:** `test_spark_store_parses_provenance_struct`, `test_writer_schema_matches_reader_expectation`.

### 3. Rejection reporting (`sec_kg/build.py`, `scripts/build_sec_knowledge_graph.py`)
- **Fixed:** `build_graph` now returns `(nodes, edges, stats: BuildStats)` with per-reason rejection counts.
- **Fixed:** Manifest reports `input_rows_by_entity_type`, `accepted_rows`, `rejected_rows`, and `rejection_reasons` (no more negative `rejected_row_count`).
- **Fixed:** Build FAILS on non-zero exit when rejection reason prefix is not in `ALLOWED_REJECTION_REASONS` or `_*_error` patterns.
- **Tests added:** `test_malformed_row_counted_reason`, `test_unknown_entity_type_rejected`, `test_validate_rejection_reasons_pass`, `test_validate_rejection_reasons_fail_on_unknown`, `test_accepted_rows_counted`.

## Non-blocking notes

- Citation level is now conservatively filing-level for all XBRL facts (43,722/43,722) because the production corpus chunks don't contain the raw numeric values. This is correct per the spec: "chunk level only when the chunk verifiably contains the fact."
- Events (1,741) also have filing-level citations because their accession numbers don't have matching corpus chunks with the event values.
- RiskFactor nodes (1,457) still have chunk-level citations where the chunk text matches.

## Checks run

- `python3 -m pytest -q -p no:cacheprovider tests/rag` → **pass** (379 passed, 19 skipped)
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase` → **pass** (658 passed, 67 skipped, 149s)
- Offline build (`scripts/build_sec_knowledge_graph.py`) → **63,520 nodes / 136,786 edges** in 39.88s
  - XbrlFact: 43,722 (all filing-level)
  - SOURCED_FROM: 1,457 (RiskFactor only)
  - SUPERSEDES: 965
  - Accepted rows: 49,687
  - Rejected rows: 0
  - Rejection reasons: {} (all documented)
- LF line endings verified on all modified files.
- No scratch files left in repo.