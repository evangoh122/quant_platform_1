# CHECK: rag-coverage — CodeRabbit PR #28 round 3 fixes (checker: DeepSeek)

Read-only; mutations only in `git archive HEAD | tar -x -C /tmp/<dir>` copies; never run git inside a copy. Shell rule: if a command needs
quoting, write it to `/home/jianj/code/qp1-ragcov/.agentlogs/<name>.sh` and run exactly
`wsl -d Ubuntu -- bash /home/jianj/code/qp1-ragcov/.agentlogs/<name>.sh`. No .ps1/.bat files, no PowerShell wrappers, nothing in C:\temp.
Write .agents/deepseek/VERDICT-rag-coverage-coderabbit-r3.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or
"Status: CHANGES_REQUESTED", file:line.
Findings: .agents/coderabbit-pr28-round3.md (7 + 1 nitpick). Commits 55f9bc4..b232b9f (one per finding). MiMo verdict is a self-report.
Claude: offline suite 2525 passed, 0 failed.
1. For each code fix, revert just that fix in a /tmp copy → a test must FAIL; list test name + FAILED line. (Runbook is docs-only.)
2. sec_ingest_log: no f-string values in SQL; only TABLE_OR_VIEW_NOT_FOUND counts as cold start — other errors propagate (test).
3. Dry run writes nothing to sec_cik_mapping_log unless --log-dry-run (test with a recording writer).
4. `python3 -m ruff check tests/rag/test_sec_rag_ingest.py` (or `uvx ruff check`) has no F821.
5. 77dac0a (nitpick perf: O(1) chunk lookup) — behaviour unchanged (same results), covered by existing tests.
