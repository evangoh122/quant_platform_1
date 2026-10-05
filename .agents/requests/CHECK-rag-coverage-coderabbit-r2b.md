# CHECK: rag-coverage CodeRabbit r2b — re-check of your blocking finding (checker: DeepSeek)

Read-only; mutations only in `git archive HEAD | tar -x -C /tmp/<dir>` copies. Run WSL commands directly (`wsl -d Ubuntu -- bash -lc '<cmd>'`),
never via PowerShell wrappers or C:\temp scripts. Write .agents/deepseek/VERDICT-rag-coverage-coderabbit-r2b.md between
===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Your r2 verdict: .agents/deepseek/VERDICT-rag-coverage-coderabbit-r2.md (only blocker: TestDiscoveryCikPerFiling was not mutation-proof).
Fix commit 164fd44 (Claude tiny fix): the accession prefix is a filing agent (0001193125, outside the CIK group) and the test is parametrized over
both group members. Claude: reverting `plan_cik = discovery_cik or next(iter(ticker_ciks))` → `next(iter(ticker_ciks))` fails 1 of 2 cases under
PYTHONHASHSEED=1,2,3; tests/rag/test_sec_rag_ingest.py 203 passed.
Re-run that revert under several PYTHONHASHSEED values (each must fail at least one case), confirm the other five reverts still fail, and run
`python3 -m pytest tests/rag -q`.
