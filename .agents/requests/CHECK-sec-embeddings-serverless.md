# CHECK: sec_embeddings job fixes for serverless (checker; Codex luna while DeepSeek is out of balance)

Branch fix/sec-embeddings-serverless-libs = main + three Claude config/runtime fixes found while running the owner-approved embeddings rebuild on
2026-10-06 (each failure was observed live on Databricks):
- 8ef8cb2 resources/jobs.yml: drop the `libraries:` block from the serverless sec_embeddings task — `bundle deploy` failed with
  "Libraries field is not supported for serverless task" (deps are already in the environment spec).
- 1128a16 pipelines/build_sec_embeddings.py: `__file__` is undefined in a serverless spark_python_task (NameError) → fall back to sys.argv[0].
- 5dadacb pipelines/build_sec_embeddings.py: inside a Databricks job use the ambient SparkSession (DATABRICKS_RUNTIME_VERSION set); Databricks Connect's
  `.serverless()` builder does not exist there (AttributeError).
After these the job ran (run 683110311969983) and is writing embeddings.
Check: (1) the same three problems in OTHER entry points / jobs (grep `__file__` in pipelines/*.py used as python_file by resources/jobs.yml;
`DatabricksSession.builder.serverless` in job entry points; `libraries:` on serverless tasks) — list each with file:line; (2) tests: is there a test that would
have caught any of these (e.g. a jobs.yml lint for libraries+environment_key; an entry-point import test without __file__)? If not, say what minimal test
should be added. Read-only; print the verdict between ===VERDICT START=== / ===VERDICT END=== with Status: APPROVED or Status: CHANGES_REQUESTED and file:line.
