# CHECK: rag-eval-harness-round10 (checker: DeepSeek)

Read-only for source: do NOT edit code or tests. Mutation proofs go in /tmp copies (cp -r the repo to /tmp/rag-eval-harness-round10-mut-*).
Write your verdict to .agents/deepseek/VERDICT-rag-eval-harness-round10.md between ===VERDICT START=== and ===VERDICT END===,
with "Status: APPROVED" or "Status: CHANGES_REQUESTED", numbered findings with file:line evidence, test counts,
and mutation-proof results. MiMo's own .agents/mimo/VERDICT-* is a self-report, not evidence.

Build request: .agents/requests/BUILD-rag-eval-harness-round10.md
Previous checker verdict (what had to be fixed): .agents/deepseek/VERDICT-rag-eval-harness-round9.md
Commits to check: cfe2f90..HEAD
For EVERY item in the build request: verify it is done (file:line), and re-run each requested mutation proof yourself in /tmp —
the named test must FAIL on the mutated copy. Check no test was deleted or weakened: git diff cfe2f90..HEAD -- tests.
Run: python -m pytest tests/rag -q and pyspark hidden (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps). Key: production parity compares search_sec_filings' RETURNED scores (perturbing only the returned dicts must fail); pytest-timeout in CI + requirements; socket default timeout restored; loopback tests import the real function.
