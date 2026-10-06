# VERDICT: serverless-entrypoints-r3 — MiMo
**Status:** APPROVED
**Round:** 3

## Blocking findings
(none)

## Non-blocking notes
- `lakebase_analytics.py` imports `_runtime` late (inside `main()` at line 670) rather than at module level; works fine because the bootstrap runs at module level, but could be consolidated for consistency.
- The old `sys.path.insert(0, str(repo_root()))` calls were removed from 5 files since the bootstrap now handles path setup before `_runtime` is imported.

## Checks run
- `python3 -m pytest tests/test_jobs_serverless.py -xvs` → 15/15 passed
- `test_entry_points_run_from_unrelated_cwd` → pass (all 6 entry points exit 0 with `--help` from temp dir, PYTHONPATH removed)
- `test_mutation_remove_bootstrap_fails` → pass (removing bootstrap from run_silver_gold.py causes ModuleNotFoundError)
- `test_no_bare_dunder_file_in_entry_points` → pass (bootstrap uses `globals().get("__file__")` not bare `__file__`)
- `test_static_scan_covers_all_python_files` → pass (all 6 expected files discovered)

## Changes
- `pipelines/run_silver_gold.py`: bootstrap before `_runtime` import, removed old `sys.path.insert`
- `ml/run_ablation.py`: bootstrap before `_runtime` import, removed old `sys.path.insert`
- `pipelines/build_sec_knowledge_graph.py`: added `import os`, bootstrap before `_runtime` import, removed old `sys.path.insert`
- `pipelines/build_sec_embeddings.py`: bootstrap before `_runtime` import, removed old `sys.path.insert`
- `pipelines/sec_rag_ingest.py`: bootstrap before `_runtime` import, removed old `sys.path.insert` and comment
- `pipelines/lakebase_analytics.py`: added `import os`, bootstrap at module level before logging setup
- `tests/test_jobs_serverless.py`: added `test_entry_points_run_from_unrelated_cwd` and `test_mutation_remove_bootstrap_fails`