# VERDICT: rag-coverage-round13 — MiMo
**Status:** APPROVED
**Round:** 13

## Blocking findings
- None.

## Changes made

### 1. User-Agent resolution (`pipelines/sec_rag_ingest.py`)
- Added `_resolve_user_agent(secret_scope, secret_key)` helper with three-tier resolution:
  1. Env `SEC_EDGAR_USER_AGENT` (highest priority)
  2. `dbutils.secrets.get` (Databricks cluster notebooks)
  3. `WorkspaceClient().secrets.get_secret_value` with base64 decode (serverless SDK)
- Added `_validate_user_agent(user_agent)` to enforce non-empty and non-placeholder checks
- Added constants `DEFAULT_SECRET_SCOPE = "evangoh_capstone"` and `DEFAULT_SECRET_KEY = "sec_edgar_user_agent"`
- Updated `run_ingest()` signature with `user_agent_secret_scope` and `user_agent_secret_key` params
- Updated `main()` CLI with `--user-agent-secret-scope` and `--user-agent-secret-key` args
- Never logs the actual value — only logs `source=env` or `source=secret (dbutils/sdk, scope=...)`

### 2. `resources/jobs.yml`
- sec_rag_ingest task now passes `--user-agent-secret-scope evangoh_capstone` and `--user-agent-secret-key sec_edgar_user_agent` as CLI parameters

### 3. `docs/SEC_RAG_COVERAGE_RUNBOOK.md`
- Added "Secret Setup" section documenting `databricks secrets put-secret evangoh_capstone sec_edgar_user_agent`
- Updated Prerequisites to reference the new secret-based approach

### 4. Tests (`tests/rag/test_sec_rag_ingest.py`)
- `TestResolveUserAgent` (8 tests): env wins, empty falls through, missing both names scope/key, placeholder rejected, value not in logs, SDK base64 decode, mutation skip-base64-fails, custom scope/key passthrough
- `TestValidateUserAgent` (5 tests): valid passes, empty/None/placeholder raises
- `TestJobsYmlSecretParams` (1 test): parses jobs.yml and asserts secret params present with correct defaults
- `TestRunIngestUserAgentResolution` (5 tests): env works, missing env raises, placeholder raises, main() passes args, main() defaults
- Mutation-proof tests: skip base64 decode → FAIL; log the value → FAIL

## Checks run
- `python3 -m pytest tests/rag/test_sec_rag_ingest.py -q -k "TestResolveUserAgent or TestValidateUserAgent or TestJobsYmlSecretParams or TestRunIngestUserAgentResolution"` → 20 passed
- `python3 -m pytest tests/rag tests/bronze -q` → 210 passed, 62 failed (all pre-existing: missing loguru/beautifulsoup4/langchain_core on Windows env), 18 skipped
- No regressions introduced by this change

## Files touched
- `pipelines/sec_rag_ingest.py` — _resolve_user_agent, _validate_user_agent, run_ingest signature, main() CLI args
- `resources/jobs.yml` — sec_rag_ingest task parameters
- `docs/SEC_RAG_COVERAGE_RUNBOOK.md` — secret setup documentation
- `tests/rag/test_sec_rag_ingest.py` — 29 new test methods across 4 test classes