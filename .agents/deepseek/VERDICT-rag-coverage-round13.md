===VERDICT START===
# VERDICT: rag-coverage round 13 — DeepSeek (checker)
**Status:** CHANGES_REQUESTED
**Round:** 13

## Summary

The env-precedence, validation, no-log, jobs.yml param, and runbook work are all correct and well-tested. But the
**SDK secret path — the exact mechanism the round-13 blocker depends on for the serverless `sec_rag_ingest` job — is
broken**: `pipelines/sec_rag_ingest.py:127` calls `client.secrets.get_secret_value(...)`, a method that does not exist
in the Databricks SDK. On a serverless `spark_python_task` (no IPython kernel → no `dbutils`) the job still raises at
startup, dry-run included. The two coverage tests that claim to prove the SDK path also mock the same non-existent
method, so they pass only because they encode the same bug.

## Blocking findings

1. `pipelines/sec_rag_ingest.py:127` — `resp = client.secrets.get_secret_value(scope=..., key=...)` uses a method
   that is not on `databricks.sdk` `SecretsAPI`. Verified against the installed SDK (`databricks-sdk 0.146.0`, pinned
   `>=0.20.0` in `requirements.txt:4`): `dir(SecretsAPI)` contains only `get_secret`, `put_secret`, `delete_secret`,
   `list_secrets`, `create_scope`, `delete_scope`, `list_scopes`, `get_acl`, `put_acl`, `delete_acl`, `list_acls`.
   There is no `get_secret_value`. The established codebase pattern also uses `get_secret`
   (`notebooks/refresh_bronze_options.py:366` → `w.secrets.get_secret(SECRET_SCOPE, key_name).value`).
   → Failure scenario: on the serverless `sec_rag_ingest` job there is no IPython kernel, so the `dbutils` branch at
   `:109-120` silently fails; the SDK branch raises `AttributeError: 'SecretsAPI' object has no attribute
   'get_secret_value'`, which is swallowed by `except Exception: pass` at `:135`, and `_resolve_user_agent` then raises
   `ValueError("SEC_EDGAR_USER_AGENT not found …")` at `:138-141`. The job fails at startup — the precise defect this
   round was opened to fix. `get_secret` returns a `GetSecretResponse` whose `.value` is the base64 byte-string
   (`databricks.sdk.service.workspace.GetSecretResponse.value`, confirmed), so the `base64.b64decode` at `:129` is
   correct **only once the method name is fixed to `get_secret`** (the BUILD request `BUILD-rag-coverage-round13.md`
   item 1 explicitly mandates `WorkspaceClient().secrets.get_secret(...)`).

2. `tests/rag/test_sec_rag_ingest.py:3003` and `:3037` — `mock_client.secrets.get_secret_value.return_value = mock_response`
   mock the non-existent method. These tests pass only because the production code uses the same wrong name, giving a
   false green on the exact property the round is meant to guarantee. If the code is corrected to `get_secret`, the
   mocked `get_secret` returns a `MagicMock`, `resp.value` is a `MagicMock`, `base64.b64decode(MagicMock)` raises, the
   exception is swallowed, and `_resolve_user_agent` raises `ValueError` → both `test_sdk_base64_decode` and
   `test_sdk_base64_decode_mutation_skip_fails` would FAIL. The mutation-proof tests are therefore only mutation-proof
   against a codebase that keeps the broken method name.

## Non-blocking notes

- `pipelines/sec_rag_ingest.py:110` — dbutils detection via `IPython.get_ipython().user_ns.get("dbutils")` deviates
  from the repo's working pattern `globals().get("dbutils")` (`notebooks/refresh_bronze_options.py:348`,
  `notebooks/02_ingest_sec_edgar.py:38`). `dbutils` is injected into IPython's `user_global_ns`, not always `user_ns`,
  so even in a classic notebook this may miss. Secondary to finding 1, but worth aligning.
- `docs/SEC_RAG_COVERAGE_RUNBOOK.md` — the illustrative values (`… your-email@example.com`) contain `example`, which
  `_validate_user_agent` (`:146`) rejects. Docs-only; if a reader copies them literally the value is rejected at
  startup. Consider a non-placeholder example (e.g. `YourCompany ops@yourcompany.com`).
- `dbutils.secrets.get` returns the plain value (no base64), so the missing decode on the dbutils path at `:112` is
  correct as-is.

## What is correct (verified)

- **env wins over secret**: `:102-105` checks env first and returns immediately; `TestResolveUserAgent.test_env_wins_over_secret` passes.
- **missing both → clear error naming scope/key**: `:138-141` includes `scope='{secret_scope}', key='{secret_key}'`; `test_missing_both_raises_clear_error_naming_secret` asserts both names.
- **placeholder rejected**: `:146` (`"example" in user_agent.lower()`); `TestValidateUserAgent` (5 cases) pass.
- **value never logged**: only `source=env`/`source=secret (…, scope=%s)` logged; `test_value_never_appears_in_log` and `test_log_value_leak_mutation_fails` pass.
- **jobs.yml passes scope/key + argparse accepts**: `resources/jobs.yml:61-72` passes `--user-agent-secret-scope evangoh_capstone` / `--user-agent-secret-key sec_edgar_user_agent`; `main()` args at `sec_rag_ingest.py:2061-2070`; `TestJobsYmlSecretParams` and `test_main_passes_secret_args_to_run_ingest` pass.
- **runbook documents creation without a real value**: `docs/SEC_RAG_COVERAGE_RUNBOOK.md` "Secret Setup" uses `databricks secrets put-secret evangoh_capstone sec_edgar_user_agent` with no committed value.

## Checks run

- `python3 -m pytest tests/rag tests/bronze -q` (WSL, all deps present) → **693 passed, 36 skipped, 0 failed** (21.2s) — no rounds 10–12 regression.
- `python3 -m pytest tests/rag/test_sec_rag_ingest.py -q -k "ResolveUserAgent or ValidateUserAgent or JobsYml or RunIngestUserAgent"` → **20 passed**.
- `python3 -c "from databricks.sdk.service import workspace; print([m for m in dir(workspace.SecretsAPI) if not m.startswith('_')])"` → `['create_scope','delete_acl','delete_scope','delete_secret','get_acl','get_secret','list_acls','list_scopes','list_secrets','put_acl','put_secret']` — no `get_secret_value`.
- `grep -rn "get_secret_value" databricks/sdk/service/workspace.py` → only `def get_secret` (no `get_secret_value`).

## Required fix

- `pipelines/sec_rag_ingest.py:127` → `client.secrets.get_secret(scope=secret_scope, key=secret_key)` (and update the
  docstring at `:95`).
- `tests/rag/test_sec_rag_ingest.py:3003` / `:3037` → mock `get_secret` instead of `get_secret_value`.
- Re-run `python3 -m pytest tests/rag tests/bronze -q`.
===VERDICT END===
