# VERDICT: post-merge-round7 — MiMo
**Status:** APPROVED
**Round:** 7

## Blocking findings
- None.

## Non-blocking notes
- Added `user_safe` flag to `EmbeddingConfigError` to distinguish secret-free messages (dim/model mismatch) from ones that may contain tokens. The handler in `tools_retrieval.py` passes through the error message only when `user_safe=True`, keeping the hardcoded safe message for all other `EmbeddingConfigError` raises.
- Three existing tests that used `match="dimension mismatch"` needed updating to match the new message format (`dim .* != stored`). These tests validate the actual `vector_search` behavior, not the handler path.
- Mixed stored dimensions remain a `CorpusUnavailableError` (data problem, not config).

## Checks run
- `python3 -m pytest -q -p no:cacheprovider tests/rag tests/test_schema_env_override.py` → 303 passed, 19 skipped
- Same suite with pyspark/databricks.connect hidden → 303 passed, 19 skipped
- Tightened tests proven to fail on original HEAD (model mismatch test failed: "ST_EMBEDDING_MODEL" missing from hardcoded message)
- LF line endings confirmed on all modified files
- No scratch files, no secrets committed, `.agents/dispatch.sh` untouched