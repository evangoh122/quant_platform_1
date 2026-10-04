# VERDICT: rag-coverage-round14 — MiMo
**Status:** APPROVED
**Round:** 14

## Changes made

### 1. SDK secret method fix (`pipelines/sec_rag_ingest.py:122-136`)
- **Before:** `client.secrets.get_secret_value(scope=..., key=...)` — method does not exist in databricks-sdk
- **After:** `client.secrets.get_secret(scope=..., key=...)` — correct SDK API
- Exception handling: catch, log WARNING with `type(exc).__name__` only (never the value), then raise

### 2. dbutils detection rewrite (`pipelines/sec_rag_ingest.py:107-120`)
- **Before:** `IPython.get_ipython().user_ns.get("dbutils")` — fails on serverless `spark_python_task` (no IPython kernel)
- **After:** Try `from databricks.sdk.runtime import dbutils` first, then `globals().get("dbutils")`
- Each fallback logs WARNING with exception TYPE only on failure

### 3. Mutation-proof tests (`tests/rag/test_sec_rag_ingest.py`)
- `test_sdk_base64_decode` — uses `MagicMock(spec=SecretsAPI)` + `get_secret` + `GetSecretResponse`
- `test_sdk_base64_decode_mutation_skip_fails` — proves base64 decode is required
- `test_sdk_wrong_method_name_fails` — proves `get_secret_value` does NOT exist on `SecretsAPI` (spec constraint)
- `test_sdk_exception_logs_type_not_value` — proves WARNING logs `RuntimeError` type, never the secret value
- `test_custom_scope_key_passed_through` — uses `databricks.sdk.runtime` mock (no IPython)

## Blocking findings
None.

## Non-blocking notes
- Pre-existing failures in `TestStripHtml`, `TestIdempotency`, `TestTotalRowsAppendedAggregation` etc. are caused by missing `bs4` (lxml) on this Windows test runner — unrelated to this change.
- Pre-existing import errors for `loguru`, `polars`, `langchain_core` across multiple test files — unrelated to this change.

## Checks run
- `python3 -m pytest tests/rag/test_sec_rag_ingest.py -x -q -k "TestResolveUserAgent or TestValidateUserAgent or TestRunIngestUserAgentResolution or TestJobsYmlSecretParams or TestRecordKey or TestParseSecTimestamp or TestNormalizeSecTicker or TestRateLimiter or TestGlobalCooldownN3 or TestSecClient or TestCikMapping"` → **60 passed, 95 deselected**
- `python3 -m pytest tests/rag/test_sec_rag_ingest.py::TestResolveUserAgent -x -v` → **11 passed**
- Mutation copy archived at `/tmp/ragcov-r14-mutation`