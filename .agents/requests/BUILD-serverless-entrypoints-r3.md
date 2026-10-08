# BUILD: serverless entry points round 3 (Codex sol CHANGES_REQUESTED — import bootstrap)

You are MiMo. Branch `fix/sec-embeddings-serverless-libs` (stay on it). Read `.agents/codex/VERDICT-serverless-entrypoints.md`. LF endings, never touch
`.agents/dispatch.sh`, no Databricks. Shell rule: if quoting is hard, write to `/home/jianj/code/qp1-main/.agentlogs/<name>.sh` and run
`wsl -d Ubuntu -- bash /home/jianj/code/qp1-main/.agentlogs/<name>.sh`. No .ps1/.bat, no PowerShell wrappers, nothing in C:\temp. Stage only files you change.
COMMIT; verdict `.agents/mimo/VERDICT-serverless-entrypoints-r3.md`.
Entry points import `pipelines._runtime` BEFORE the repo root is on sys.path, so `cd /tmp && env -u PYTHONPATH python3 <repo>/pipelines/run_silver_gold.py --help`
fails with ModuleNotFoundError (also ml/run_ablation.py:22, build_sec_knowledge_graph.py:18, build_sec_embeddings.py:34, sec_rag_ingest.py:39).
1. In every resources/jobs.yml python_file, add a tiny inline bootstrap BEFORE any package import that puts the repo root on sys.path without needing `__file__`
   (`_p = globals().get("__file__") or sys.argv[0]; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(_p))))` — adjust depth per file), then import
   from pipelines._runtime.
2. Test: a subprocess test that runs `python3 <file> --help` for EVERY python_file in resources/jobs.yml with cwd=/tmp-style temp dir and PYTHONPATH removed from
   env, asserting exit 0 (mock-free; --help must not touch Spark/network — make argparse run before any Spark/network work where needed). Mutation: remove the
   bootstrap from one entry point → that subprocess test fails.
