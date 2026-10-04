# BUILD-rag-coverage round 13 — IMPLEMENT NOW (Claude final-review blocker)

You are MiMo. Commit per item, LF endings, do not touch `.agents/dispatch.sh`, never delete/weaken tests, capture the red phase,
mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>`.

Blocker: on Databricks the `sec_rag_ingest` job can never start. `pipelines/sec_rag_ingest.py:~1143` requires env
`SEC_EDGAR_USER_AGENT`, but `resources/jobs.yml` (sec_rag_ingest task, serverless spark_python_task) sets no env and no secret,
so the job raises at startup (dry-run included).

1. Resolve the User-Agent in this order: env `SEC_EDGAR_USER_AGENT`; else a Databricks secret given by CLI args
   `--user-agent-secret-scope` / `--user-agent-secret-key` (defaults: scope `evangoh_capstone`, key `sec_edgar_user_agent`).
   Read the secret with `dbutils.secrets.get` when available on the cluster, else `WorkspaceClient().secrets.get_secret(...)`
   whose `.value` is BASE64 — decode it. Never log/print the value (log only "source=env|secret").
   Keep the existing validation (non-empty, not a placeholder containing "example").
2. `resources/jobs.yml`: pass the scope/key parameters to the sec_rag_ingest task. Document in `docs/SEC_RAG_COVERAGE_RUNBOOK.md`
   how to create the secret (`databricks secrets put-secret evangoh_capstone sec_edgar_user_agent`), without any real value.
3. Tests: env wins over secret; secret path base64-decodes the SDK value; missing both → clear error naming the secret; placeholder
   rejected; value never appears in caplog/stdout (seed a fake value and assert absence). Mutation: skip base64 decode → FAIL;
   log the value → FAIL. Also a test that parses resources/jobs.yml and asserts the sec_rag_ingest task passes the secret params.
Run: python3 -m pytest tests/rag tests/bronze -q. Verdict: .agents/mimo/VERDICT-rag-coverage-round13.md.
