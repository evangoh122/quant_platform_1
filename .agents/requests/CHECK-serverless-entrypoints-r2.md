# CHECK round 2: serverless-safe job entry points (checker; Codex luna while DeepSeek is out of balance)

Read-only; mutations only in /tmp copies made with `git archive HEAD`. Print the verdict to stdout between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Your previous verdict: .agents/deepseek-fallback/VERDICT-sec-embeddings-serverless.md (file:line list of remaining __file__, .serverless(True), libraries).
Spec .agents/requests/BUILD-serverless-entrypoints.md. Latest commit on fix/sec-embeddings-serverless-libs. Claude: offline suite 2534 passed; bundle validate OK.
1. Every item in your previous list is fixed (show file:line); every python_file in resources/jobs.yml uses pipelines/_runtime.py.
2. Mutations, each must fail tests/test_jobs_serverless.py: re-add `libraries` to a serverless task; reintroduce a module-level `__file__` in one entry point;
   call `.serverless(True)` inside a runtime path.
3. Local (non-runtime) behaviour unchanged: get_spark() without DATABRICKS_RUNTIME_VERSION still uses Databricks Connect serverless; repo_root() correct.

## Round 2 delta
Your r1 verdict: .agents/deepseek-fallback/VERDICT-serverless-entrypoints.md (ml/run_ablation.py not using _runtime.py; relative output path). Fix adce056.
Claude: tests/test_jobs_serverless.py + tests/ml → 77 passed; bundle validate OK. Confirm the static scan now covers EVERY python_file in jobs.yml, the ablation
output path is absolute, and the relative-path mutation fails a test. Run the offline suite with a timeout per test if it stalls (report a stall as such).
