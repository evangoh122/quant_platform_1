# BUILD-REQUEST: rag-databricks — ROUND 4 (no silent degradation)

**Builder:** MiMo · **Checkers:** Claude, then DeepSeek

## Round 3 verified LIVE by the coordinator — keep it
- Search works with **no manual session** (`as_of=2025-01-01` → only the 2024-11-21 NVDA filing).
- Missing embeddings table → structured `{"error": "retrieval_unavailable", ...}`, not `[]`. 36 tests pass.

## Remaining defects (`agent/tools_retrieval.py`)
1. **Silent degraded fallback** (`:127-140`). Any non-`CorpusUnavailableError` exception falls back to the
   old substring filter and returns ordinary-looking results. The agent cannot tell it got worse
   evidence. Remove the fallback, **or** keep it but tag every fallback result with
   `"retrieval_mode": "substring_fallback"` plus a top-level warning field, and tag normal results
   `"retrieval_mode": "hybrid"`. Pick one and say which.
2. **`_spark()` (`:27-29`) still uses `SparkSession.builder.getOrCreate()`**, which databricks-connect
   rejects outside a Databricks runtime — so the fallback path itself crashes there. Reuse the session
   helper from `api/services/hybrid_retriever.py` (DatabricksSession outside a runtime).
3. **Raw exception text in the result** (`"message": f"... {e}"`). That text can reach the LLM and the UI.
   Return a fixed message; log the exception server-side only.

## Tests
- A non-corpus exception never returns untagged results (whichever option you chose).
- `_spark()` selects DatabricksSession outside a runtime (mock).
- The unavailable result contains no exception text.
- Existing 36 tests still pass.

Edit only `agent/tools_retrieval.py`, `api/services/hybrid_retriever.py`, `tests/rag/test_hybrid_retriever.py`.
LF line endings. **Commit your work.** Write `.agents/mimo/VERDICT-rag-databricks-round4.md`.
