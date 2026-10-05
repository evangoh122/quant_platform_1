# CHECK: rag-coverage round 19c (checker: DeepSeek)

Read-only on the worktree. Mutations only in `git archive HEAD | tar -x -C /tmp/<dir>` copies; never run git inside a copy.
Write .agents/deepseek/VERDICT-rag-coverage-round19c.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or
"Status: CHANGES_REQUESTED", file:line for every finding.

Spec: .agents/requests/BUILD-rag-coverage-round19c.md. Your round-19 verdict: .agents/deepseek/VERDICT-rag-coverage-round19.md.
MiMo's verdict is a self-report. Claude: `python3 -m pytest tests/rag tests/bronze -q` → 1177 passed, 36 skipped.

Verify both blocking findings are fixed, by mutation:
1. Filer CIK: mutate plan_cik back to the iteration CIK → a test fails; mutate the fetch URL to the iteration CIK → a test fails.
   Re-run your XOM scenario (1 holdings + 8 legacy, 1 shared accession, 1 already present): discovered=8, planned=7, skipped=2,
   and planned+skipped+failed == discovered. A filing whose accession prefix CIK is NOT in the group: what happens? (must not crash or
   silently mis-store).
2. repair_cik_ownership: no user value interpolated into SQL text (grep the function); `spark.sql(..., args=[...])` positional `?`
   markers work with the Databricks Connect / Spark version in requirements (check the installed pyspark/databricks-connect API);
   tickers with `'` rejected; UPDATE constrained by ticker+accession+cik; non-group target CIK refused; dry-run writes nothing; idempotent.
   Mutate: reintroduce f-string ticker → a test fails; drop the group refusal → a test fails.
3. Are the retained/added "mutation" tests real (exercise shipped code) or inline re-implementations?
