# Codex gpt-5.6-sol review — serverless entry points (saved by Claude)

===VERDICT START===
Status: CHANGES_REQUESTED

- `pipelines/run_silver_gold.py:28`: imports `pipelines._runtime` before adding the repository root to `sys.path`. Direct execution from an unrelated cwd fails immediately with `ModuleNotFoundError: No module named 'pipelines'`. The same bootstrap problem exists at `ml/run_ablation.py:22`, `pipelines/build_sec_knowledge_graph.py:18`, `pipelines/build_sec_embeddings.py:34`, and `pipelines/sec_rag_ingest.py:39`.
- `tests/test_jobs_serverless.py:358`: the cwd-independence test changes cwd only after `ml.run_ablation` has already imported successfully, so it does not catch entry-point bootstrap failures. Add a subprocess test that executes each `resources/jobs.yml` `python_file` from outside the repository with repository-specific `PYTHONPATH` removed.
- Reproduction from a `/tmp` `git archive HEAD`:
  `cd /tmp && env -u PYTHONPATH python3 <archive>/pipelines/run_silver_gold.py --help`
  fails at line 28 before argument parsing.
- Requested suite passed: 285 passed, 61 warnings.
- All four `/tmp` mutation proofs failed their guarding tests as expected: serverless `libraries`, bare `__file__`, `.serverless(True)` outside `_runtime.py`, and relative ablation output.
- No repository files were edited.
===VERDICT END===
