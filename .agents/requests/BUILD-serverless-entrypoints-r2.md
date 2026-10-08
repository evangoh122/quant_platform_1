# BUILD: serverless entry points round 2 (checker CHANGES_REQUESTED — ml/run_ablation.py)

You are MiMo. Branch `fix/sec-embeddings-serverless-libs` (stay on it). Read `.agents/deepseek-fallback/VERDICT-serverless-entrypoints.md`. LF endings, never touch
`.agents/dispatch.sh`, no Databricks. Shell rule: if quoting is hard, write to `/home/jianj/code/qp1-main/.agentlogs/<name>.sh` and run
`wsl -d Ubuntu -- bash /home/jianj/code/qp1-main/.agentlogs/<name>.sh`. No .ps1/.bat, no PowerShell wrappers, nothing in C:\temp. Stage only files you change.
COMMIT; verdict `.agents/mimo/VERDICT-serverless-entrypoints-r2.md`.
ml/run_ablation.py (a python_file in resources/jobs.yml) must use pipelines/_runtime.py (repo_root(), get_spark()) and must not write to a cwd-relative path:
write outputs under a path derived from repo_root() locally, or to a configurable `--output-dir` (default: a UC Volume path when DATABRICKS_RUNTIME_VERSION is set,
e.g. /Volumes/{catalog}/{schema}/ml_artifacts, created if missing; else repo_root()/artifacts). Extend tests/test_jobs_serverless.py so the static scan covers
EVERY python_file in jobs.yml (it missed ml/run_ablation.py) and add a test that the ablation output path is absolute and not cwd-dependent. Mutation: revert
run_ablation to a relative output path → a test fails.
