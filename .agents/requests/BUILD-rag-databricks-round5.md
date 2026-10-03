# BUILD: rag-databricks round 5 (MiMo)

Claude rejected round 4. One blocking defect, one small hardening item.

## Blocking: the fallback ignores `as_of` (point-in-time leak)
In `agent/tools_retrieval.py::search_sec_filings`, the `except Exception` substring fallback
reads `silver_sec_sections` filtered only by ticker. When `as_of` is given, it can return
filings accepted AFTER `as_of`, which is look-ahead. The hybrid path filters by `as_of`
before scoring; the fallback must do the same.

Fix:
- When `as_of` is not None, add `F.col("accepted_ts") <= <as_of as timestamp>` to the
  Spark filter BEFORE `.limit(...)`. Use the same `as_of` parsing/semantics as
  `api/services/hybrid_retriever.py`; reuse its helper if one exists.
- Order by `accepted_ts` desc before the limit, so the candidates are deterministic.
- Apply the query filter before the limit, not after: today `.limit(50)` runs first,
  so matching chunks beyond row 50 are silently missed. Push a case-insensitive
  `contains` (lower(chunk_text) contains lower(query)) into the Spark filter.
- Map the fallback rows to the same output keys as the hybrid path
  (`accession_number`, `form_type`, `accepted_ts`, `source_url`, `ticker`, `section` from
  `filing_section`, `chunk_index`, `chunk_text`). Then the agent sees one schema.
  Keep `retrieval_mode="substring_fallback"` and `_warning`.
- If the fallback itself raises, return the same structured `retrieval_unavailable` error
  dict. No raw exception text.

## Tests (tests/rag/test_hybrid_retriever.py)
- `as_of` fallback test: rows with `accepted_ts` before and after `as_of`. Only the
  earlier rows come back. Mock Spark if needed, but the assertion must fail if the
  `as_of` filter is removed. Prove it by mutating a /tmp copy and showing the test fails.
- The fallback output has the same keys as the hybrid output.
- The fallback raising returns the structured error.

## Rules
LF line endings, no CRLF. Don't touch `.agents/dispatch.sh`. Run
`python3 -m pytest tests/rag -q` and commit. Write `.agents/mimo/VERDICT-rag-databricks-round5.md`.
