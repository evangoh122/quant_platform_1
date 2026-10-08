# VERDICT: serverless-entrypoints-r2 — MiMo
**Status:** APPROVED
**Round:** 2

## Blocking findings
- (none)

## Non-blocking notes
- `ml/run_ablation.py` now imports `repo_root()` from `pipelines._runtime` and uses `sys.path.insert(0, str(repo_root()))` — consistent with all other entry points in `pipelines/`.
- `--output-dir` flag added with smart default: `/Volumes/{CATALOG}/{SCHEMA}/ml_artifacts` when `DATABRICKS_RUNTIME_VERSION` is set, else `<repo_root>/artifacts`. Both are absolute and cwd-independent.
- Old hardcoded `"ml/results"` relative path removed entirely.
- `_resolve_output_dir()` extracted as a pure function for testability.

## Checks run
- `python3 -m pytest tests/test_jobs_serverless.py -v` → 13 passed (0 failed)
  - Existing 9 tests: all pass
  - `test_static_scan_covers_all_python_files` → pass (covers all 6 python_files in jobs.yml including `ml/run_ablation.py`)
  - `test_ablation_output_path_is_absolute` → pass (local default, explicit absolute, Databricks /Volumes/ path)
  - `test_ablation_output_path_not_cwd_dependent` → pass (chdir to "/" does not change resolved path)
  - `test_mutation_ablation_relative_output_path_fails` → pass (confirms `Path("ml/results")` is relative, `_resolve_output_dir(None)` is absolute)
- `git diff --stat` → 2 files changed, 127 insertions, 3 deletions