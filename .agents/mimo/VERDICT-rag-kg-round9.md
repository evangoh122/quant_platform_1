# VERDICT: rag-kg-round9 — MiMo
**Status:** APPROVED
**Round:** 9

## Blocking findings
(none — all 6 items implemented and tested)

## Non-blocking notes
- Item #1: `pipelines/build_sec_knowledge_graph.py` now selects `F.unix_timestamp("accepted_ts").alias("accepted_epoch")` and reads `int(row.accepted_epoch)` — avoids naive `.timestamp()` on Spark-returned datetimes. `api/services/sec_knowledge_graph.py` SparkGraphStore already used this pattern; confirmed consistent.
- Item #2: `facts_timeseries` now groups by series key `(cik, concept, period_start, period_end, unit)` and keeps only the latest version per series after PIT filtering.
- Item #3: `sec_kg/build.py` `_extract_numbers_from_text`, `_normalize_number_str`, and `_chunk_text_matches_value` now use `decimal.Decimal` end-to-end. Added dual tolerance: relative (`< 0.0001`) AND absolute (`<= 0.5`) to prevent false matches on large integers differing by 1 (e.g., 9007199254740992 vs 9007199254740993).
- Item #4: MERGE statements now include `.whenNotMatchedBySourceDelete()` to remove stale rows on full rebuild.
- Item #5: `query_sec_facts` Pydantic model now has `metric: max_length=128`, `period: max_length=32`, and ticker validated against `load_allow_list()`.
- Item #6: Build pipeline and SparkGraphStore `iter_nodes`/`iter_edges` now use `toLocalIterator()` instead of `collect()`.
- Existing tests in `TestPipelineValidation` updated to use `accepted_epoch` (epoch int) instead of `accepted_ts` (datetime) to match the new Spark select pattern.
- `psycopg` and `psycopg_pool` added to `tests/rag/conftest.py` mocked modules for CI compatibility.

## Checks run
- `python -m pytest tests/rag/test_sec_knowledge_graph.py -v` → **107 passed** (0 failed)
- Mutation tests included:
  - `test_naive_datetime_to_epoch_tz_dependent` — proves `.timestamp()` on naive datetime is tz-dependent
  - `test_mutation_drop_dedupe_fails` — proves dedupe reduces 2 facts to 1
  - `test_large_integer_no_match` — proves 9007199254740992 ≠ 9007199254740993 with Decimal
  - `test_merge_has_delete_clause` — proves `whenNotMatchedBySourceDelete` is in source
  - `test_rejects_non_allowlisted_ticker` — proves non-allow-listed ticker rejected
  - `test_rejects_oversized_metric` — proves metric > 128 chars rejected
  - `test_rejects_oversized_period` — proves period > 32 chars rejected
  - `test_build_uses_to_local_iterator` — proves `toLocalIterator` in build source