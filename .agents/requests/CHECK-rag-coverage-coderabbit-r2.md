# CHECK: rag-coverage — CodeRabbit PR #28 round 2 fixes + tests (checker: DeepSeek)

Read-only; mutations only in `git archive HEAD | tar -x -C /tmp/<dir>` copies; never run git inside a copy. Run WSL commands directly
(`wsl -d Ubuntu -- bash -lc '<cmd>'`), never via PowerShell wrappers or C:\temp scripts. Write .agents/deepseek/VERDICT-rag-coverage-coderabbit-r2.md
between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Findings: .agents/coderabbit-pr28-round2.md (9). Fixes ca64736 (MiMo, committed by Claude), tests 5ef5687. MiMo verdict is a self-report
(.agents/mimo/VERDICT-rag-coverage-coderabbit-r2.md; it judged api/main.py:305 "not valid").
1. For each of the 8 fixes, revert just that fix in a /tmp copy → its named test must FAIL. List each with the FAILED line.
2. The MAJOR one: per-filing ownership check uses a parameterized single-accession query (no f-string accession), not a full-table read.
3. Judge MiMo's "not valid" on api/main.py:305 against CodeRabbit's text.
4. Offline suite `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` (tests/ml/test_hardening.py has a known flaky test).
