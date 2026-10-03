# VERDICT: rag-databricks-round4 — MiMo
**Status:** APPROVED
**Round:** 4

## Changes made

### `agent/tools_retrieval.py`
1. **`_spark()` (:26-29)** — Replaced `SparkSession.builder.getOrCreate()` with delegation to `hybrid_retriever._get_spark()`, which uses `DatabricksSession` outside a Databricks runtime.
2. **Fallback path (:127-144)** — Every result dict now carries `retrieval_mode: "substring_fallback"` and `_warning: "hybrid_retrieval_failed"`. No untagged results escape.
3. **Normal path (:104-119)** — Every result dict now carries `retrieval_mode: "hybrid"`.
4. **`CorpusUnavailableError` handler (:119-125)** — Fixed message: `"SEC filing corpus could not be loaded. Check Delta table connectivity."` — no raw exception text leaks to LLM/UI.

### `tests/rag/test_hybrid_retriever.py`
- Updated `test_returns_structured_error_on_corpus_unavailable` to match new fixed message.
- Added `test_fallback_results_tagged_with_retrieval_mode` — non-corpus exception returns tagged results.
- Added `test_unavailable_result_contains_no_exception_text` — error dict contains no leaked exception text.
- Added `test_spark_uses_databricks_session_outside_runtime` — verifies DatabricksSession used outside runtime.
- Added `test_normal_results_tagged_with_retrieval_mode_hybrid` — normal results carry `retrieval_mode: hybrid`.

## Design decision
Chose **keep fallback with tagging** over remove-fallback. The substring fallback can still return useful results when the hybrid retriever has a transient failure; tagging makes the degraded mode visible to the agent and UI.

## Blocking findings
None.

## Non-blocking notes
- The `_warning` field on fallback results is a private name (prefixed with `_`) to avoid confusion with the `error` field used for structured errors.

## Checks run
- `python3 -m pytest tests/rag/test_hybrid_retriever.py --tb=short -q` → 40 passed
- `python3 -m pytest tests/lakebase/test_symbol_validation.py --tb=short -q` → 17 passed
- `file agent/tools_retrieval.py tests/rag/test_hybrid_retriever.py` → UTF-8, no CRLF