# Checker: Codex gpt-5.6-luna (DeepSeek out of balance) — serverless r3 (saved by Claude)

===VERDICT START===
Status: APPROVED

- All six `resources/jobs.yml` Python entry points pass `--help` from `/tmp` with `PYTHONPATH` removed: `run_silver_gold.py`, `run_ablation.py`, `build_sec_embeddings.py`, `sec_rag_ingest.py`, `build_sec_knowledge_graph.py`, `lakebase_analytics.py` (`resources/jobs.yml:12,41,53,71,95,117`).
- Targeted suite: `15 passed`.
- Subprocess coverage and all required mutation proofs pass (`tests/test_jobs_serverless.py:398-432`).
- Runtime bootstrap and ambient Spark handling are correct (`pipelines/_runtime.py:23-47`).
- Repository remained unmodified.
===VERDICT END===
