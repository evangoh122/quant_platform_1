# BUILD-rag-coverage round 14 — IMPLEMENT NOW (DeepSeek CHANGES_REQUESTED on r13)

You are MiMo. Fix `.agents/deepseek/VERDICT-rag-coverage-round13.md`. Commit per item, LF endings, do not touch `.agents/dispatch.sh`,
never delete/weaken tests, capture the red phase, mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>`.

1. `pipelines/sec_rag_ingest.py:~127` calls `client.secrets.get_secret_value(...)`, which does not exist in databricks-sdk.
   Use `WorkspaceClient().secrets.get_secret(scope=..., key=...)` and base64-decode `.value`. Do NOT swallow exceptions silently:
   catch, log a WARNING with the exception TYPE only (never the value), then raise the final clear error if nothing resolved.
2. dbutils detection: serverless `spark_python_task` has no IPython kernel. Try `from databricks.sdk.runtime import dbutils` (guarded),
   then `globals().get("dbutils")`, before the SDK path; drop the IPython `user_ns` lookup.
3. Tests must use a mock constrained to the real API so a wrong method name FAILS: e.g. `create_autospec(SecretsAPI, instance=True)`
   or `MagicMock(spec=SecretsAPI)` with `get_secret.return_value = GetSecretResponse(key=..., value=base64(...))`. Mutations:
   rename back to `get_secret_value` → FAIL; skip base64 decode → FAIL; log the value → FAIL.
Claude will then run the real resolution from WSL against the workspace secret (exists: evangoh_capstone/sec_edgar_user_agent).
Run: python3 -m pytest tests/rag tests/bronze -q. Verdict: .agents/mimo/VERDICT-rag-coverage-round14.md.
