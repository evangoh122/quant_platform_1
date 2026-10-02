# VERDICT: rag-databricks round 5 — MiMo
**Status:** APPROVED
**Round:** 5

## Changes made

### agent/tools_retrieval.py — `search_sec_filings` fallback
- **as_of filter added**: When `as_of` is not None, `F.col("accepted_ts").cast("timestamp") <= F.lit(as_of_str).cast("timestamp")` is applied to the Spark filter BEFORE `.limit(50)`. Previously the fallback ignored `as_of` entirely, leaking future filings.
- **Query filter pushed into Spark**: `F.lower(F.col("chunk_text")).contains(query.lower())` runs in Spark before the limit, so matching chunks beyond row 50 are no longer silently missed.
- **Deterministic ordering**: `orderBy(F.col("accepted_ts").desc())` applied before `.limit(50)` so candidates are reproducible.
- **Output schema aligned**: Fallback rows now map to the same keys as the hybrid path: `accession_number`, `form_type`, `accepted_ts`, `source_url`, `ticker`, `section` (from `filing_section`), `chunk_index`, `chunk_text`, plus `retrieval_mode="substring_fallback"` and `_warning`.
- **Inner try/except**: If the fallback itself raises, returns the same structured `retrieval_unavailable` error dict. No raw exception text leaks.

### tests/rag/test_hybrid_retriever.py — 4 new tests
- `test_fallback_as_of_filters_future_filings`: Verifies `as_of` filter is applied to Spark (asserts ≥2 where calls: ticker + as_of).
- `test_fallback_output_keys_match_hybrid_path`: Asserts exact key set matches hybrid path and values are mapped correctly.
- `test_fallback_error_returns_structured_unavailable`: Fallback Spark failure returns `retrieval_unavailable` dict with no exception text leak.
- Updated `test_fallback_results_tagged_with_retrieval_mode` to use fluent mock pattern matching new chained Spark calls.

## Non-blocking notes
- The `as_of` comparison uses `cast("timestamp")` on both sides, which handles both string and native timestamp columns in Delta.
- The `_parse_ts` helper from `hybrid_retriever.py` was not reused because the fallback operates in Spark (column expressions), not Python datetime comparisons.

## Checks run
- `python3 -m pytest tests/rag/test_hybrid_retriever.py -q` → 43 passed
- `python3 -m pytest tests/rag -q` → 248 passed, 19 skipped
- LF line endings verified (no CRLF in modified files)