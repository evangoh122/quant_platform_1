# Checker: Codex gpt-5.6-luna (DeepSeek out of balance) — sec-embeddings-serverless (saved by Claude)

===VERDICT START===
Status: CHANGES_REQUESTED

Unfixed serverless issues:

- `pipelines/build_sec_knowledge_graph.py:20` — uses `__file__`.
- `pipelines/run_silver_gold.py:30,37` — uses `__file__`.
- `pipelines/sec_rag_ingest.py:39,546` — uses `__file__`.
- `pipelines/run_silver_gold.py:86` — calls `DatabricksSession.builder.serverless(True)`.
- `pipelines/sec_rag_ingest.py:1878,1953,1971,1988,2026,2177,2282,2349,2465` — calls `DatabricksSession.builder.serverless(True)`.
- `resources/jobs.yml:126` — `libraries: []` remains on a serverless task.

Tests: `21 passed`. Existing tests do not catch these failures. Add tests that:
1. Reject `libraries` on serverless tasks.
2. Validate every configured Python entry point works without `__file__`.
3. Verify job entry points use ambient `SparkSession` when `DATABRICKS_RUNTIME_VERSION` is set.

===VERDICT END===
