# CHECK round 3: serverless entry points — import bootstrap (checker; Codex luna while DeepSeek is out of balance)

Read-only; mutations only in /tmp copies made with `git archive HEAD`. Print the verdict to stdout between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Codex sol finding: .agents/codex/VERDICT-serverless-entrypoints.md (entry points imported pipelines._runtime before the repo root was on sys.path). Fix 3b77676.
Claude: tests/test_jobs_serverless.py → 15 passed; `cd /tmp && env -u PYTHONPATH python3 <repo>/pipelines/run_silver_gold.py --help` prints usage.
1. For EVERY python_file in resources/jobs.yml: `cd /tmp && env -u PYTHONPATH python3 <archive>/<file> --help` exits 0 (list each).
2. The new subprocess test covers every python_file; mutation: remove the bootstrap from one entry point → that test fails.
3. Earlier mutations (libraries on serverless; module-level __file__; .serverless(True) in a runtime path; relative ablation output) still fail.
