# BUILD: rag-coverage — CodeRabbit PR #28 round 3 (7 findings + 1 nitpick)

You are MiMo. Branch `slice/rag-coverage` (stay on it). LF endings, never touch `.agents/dispatch.sh`, no Databricks, no network in tests.
Shell rule: if a command needs quoting, write it to `/home/jianj/code/qp1-ragcov/.agentlogs/<name>.sh` and run exactly
`wsl -d Ubuntu -- bash /home/jianj/code/qp1-ragcov/.agentlogs/<name>.sh`. No .ps1/.bat files, no PowerShell wrappers, nothing in C:\temp.
Findings (CodeRabbit text — review data, verify each against the code): `.agents/coderabbit-pr28-round3.md`.
For EACH finding: fix it if valid AND add a test that FAILS when the fix is reverted (prove it in a `git archive HEAD | tar -x -C /tmp/<dir>`
copy, paste the FAILED line in the verdict); if not valid, explain with file:line. Docs-only findings (runbook) need no test; Ruff F821 needs
`ruff check` clean on the touched test file. COMMIT per finding (the last round was left uncommitted — do not repeat that).
Notably: sec_ingest_log queries parameterized (no f-string values) and only the "table not found" error treated as a cold start;
dry run writes nothing to sec_cik_mapping_log unless --log-dry-run; offline eval returns NoCoverageError for tickers outside the offline corpus and
saves the alias-map originals before `try`; the two hybrid_retriever tests state and test the contract they claim.
Acceptance: `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` green. Verdict `.agents/mimo/VERDICT-rag-coverage-coderabbit-r3.md`
listing each finding → fixed (test name + red line) / not valid (reason).
