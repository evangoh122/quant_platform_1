# VERDICT: rag-coverage-round16e — MiMo
**Status:** APPROVED
**Round:** 16e

## Blocking findings
None.

## Non-blocking notes
- 5 pre-existing failures in `test_merge_metrics.py` (PySpark `IntegerType` import error) — unrelated to this change.
- `test_langgraph_engine.py` collection error (`ModuleNotFoundError: No module named 'api.services.rag_engine'`) — pre-existing, unrelated.

## Checks run
- `python3 -m pytest tests/rag tests/bronze -q --ignore=tests/rag/test_langgraph_engine.py` → 1108 passed, 5 failed (pre-existing), 50 skipped
- `python3 -m pytest tests/rag/test_hybrid_retriever.py -q -k "test_fallback_output_keys_match_hybrid_path or test_fallback_as_of_filters_future_filings"` → 2 passed

## Changes made
- `tests/rag/test_hybrid_retriever.py`:
  - **~line 1300** `test_fallback_output_keys_match_hybrid_path`: Restored main-parent strength. Now verifies SUCCESSFUL fallback output contract with all mapped fields: `chunk_id`, `accession_number`, `form_type`, `accepted_ts`, `source_url`, `ticker`, `section`, `chunk_index`, `chunk_text`, `retrieval_mode="substring_fallback"`, `_warning="hybrid_retrieval_failed"`. Also validates field values match the mock row.
  - **~line 1356** `test_fallback_as_of_filters_future_filings`: Restored main-parent strength. Uses two rows (past `2024-06-01` + future `2026-01-01`), tracks `where_calls` list via side_effect, asserts `len(where_calls) >= 2` (ticker + as_of filters both applied). Verifies PIT predicate is load-bearing.

## Mutation coverage
- **Remove PIT predicate** (`agent/tools_retrieval.py:~161`): `test_fallback_as_of_filters_future_filings` would fail — only 1 where call (ticker) instead of ≥2.
- **Drop `source_url` from fallback output** (`agent/tools_retrieval.py:~187`): `test_fallback_output_keys_match_hybrid_path` would fail — key set mismatch and value assertion.