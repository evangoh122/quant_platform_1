# REVIEW: serverless-safe Databricks job entry points (reviewer: Codex sol)

Branch fix/sec-embeddings-serverless-libs (off main). Running the owner-approved SEC embeddings rebuild on 2026-10-06 failed three times on Databricks
serverless: `libraries` on a serverless task (bundle deploy rejected), `__file__` undefined in spark_python_task (NameError), and
`DatabricksSession.builder.serverless` inside a job runtime (AttributeError). Claude tiny-fixed build_sec_embeddings (8ef8cb2, 1128a16, 5dadacb) and the job then
ran. The checker found the same classes in other entry points → MiMo: pipelines/_runtime.py (repo_root(), get_spark()) used by every python_file in
resources/jobs.yml, no libraries on serverless tasks, ml/run_ablation absolute output path, tests/test_jobs_serverless.py lint (commits after 6e721c0 … adce056).
Checker (Codex luna, DeepSeek out of balance): r1 CHANGES_REQUESTED → r2 APPROVED (.agents/deepseek-fallback/VERDICT-serverless-entrypoints-r2.md).
Claude: offline suite 2534 passed (r1), 77 targeted passed (r2); bundle validate OK.
Run `python3 -m pytest tests/test_jobs_serverless.py tests/ml tests/rag/test_sec_rag_ingest.py -q` (the full suite can stall in your sandbox — say so).
Mutation proofs only in /tmp via `git archive HEAD`. Judge: local behaviour unchanged; job behaviour correct on serverless; nothing else in jobs depends on
cwd or __file__. Print the verdict between ===VERDICT START=== / ===VERDICT END=== with "Status: APPROVED" or "Status: CHANGES_REQUESTED" and file:line. Do not edit files.
