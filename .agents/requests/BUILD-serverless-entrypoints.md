# BUILD: make every Databricks job entry point run on serverless (owner-approved embeddings run exposed 3 classes of bug)

You are MiMo. Branch `fix/sec-embeddings-serverless-libs` (worktree qp1-main; stay on it). LF endings, never touch `.agents/dispatch.sh`, no Databricks.
Shell rule: if quoting is hard, write to `/home/jianj/code/qp1-main/.agentlogs/<name>.sh` and run `wsl -d Ubuntu -- bash /home/jianj/code/qp1-main/.agentlogs/<name>.sh`.
No .ps1/.bat, no PowerShell wrappers, nothing in C:\temp. Stage only files you change. COMMIT per item; verdict `.agents/mimo/VERDICT-serverless-entrypoints.md`.
Read `.agents/deepseek-fallback/VERDICT-sec-embeddings-serverless.md` (file:line list). Claude already fixed pipelines/build_sec_embeddings.py (commits 1128a16,
5dadacb) — reuse that behaviour, do not regress it.
1. Add `pipelines/_runtime.py` with `repo_root()` (`globals().get("__file__") or sys.argv[0]`-style, robust in serverless spark_python_task) and
   `get_spark()` (ambient `SparkSession.builder.getOrCreate()` when DATABRICKS_RUNTIME_VERSION is set; else `DatabricksSession.builder.serverless(True)`).
   Use them in every python_file referenced by resources/jobs.yml (build_sec_embeddings, build_sec_knowledge_graph, run_silver_gold, sec_rag_ingest,
   lakebase_analytics, ml/run_ablation, ingest scripts …) — replace each module-level `__file__` sys.path hack and each direct
   `DatabricksSession.builder.serverless(True)` in code that runs inside jobs. Keep local (outside-runtime) behaviour identical.
   `Path(__file__)` used to locate config files (sec_rag_ingest.py:546) → use repo_root().
2. resources/jobs.yml:126 `libraries: []` on a serverless task → remove (deps belong in environments).
3. Tests (tests/test_jobs_serverless.py): parse resources/jobs.yml — no task with `environment_key` has a `libraries` key; every `python_file` exists;
   static scan of each job entry point: no bare `__file__` at module level and no `DatabricksSession.builder.serverless` outside pipelines/_runtime.py;
   `get_spark()` returns the ambient session when DATABRICKS_RUNTIME_VERSION is set (monkeypatch a fake pyspark SparkSession); `repo_root()` works when
   `__file__` is absent (exec the module source without it). Named mutations: re-add `libraries` to a serverless task → fails; reintroduce a module-level
   `__file__` in one entry point → fails; call `.serverless(True)` inside a runtime → fails.
Acceptance: offline suite `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` green.
