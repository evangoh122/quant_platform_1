# Checker: Codex gpt-5.6-luna (DeepSeek out of balance) — serverless-entrypoints (saved by Claude)

===VERDICT START===
Status: CHANGES_REQUESTED

- `ml/run_ablation.py:14-25` — configured `python_file` does not use `pipelines/_runtime.py`; its relative output path also remains serverless-unsafe.
- `tests/test_jobs_serverless.py`: targeted suite passes (9 passed).
- Required mutations all fail as expected.
- Local/runtime Spark and `repo_root()` checks pass.
- Offline suite was interrupted after stalling at 19%.
===VERDICT END===
