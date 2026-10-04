# CHECK: rag-kg-round8 (checker: DeepSeek)

Read-only for source: do NOT edit code or tests. Mutation proofs go in /tmp copies (cp -r the repo to /tmp/rag-kg-round8-mut-*).
Write your verdict to .agents/deepseek/VERDICT-rag-kg-round8.md between ===VERDICT START=== and ===VERDICT END===,
with "Status: APPROVED" or "Status: CHANGES_REQUESTED", numbered findings with file:line evidence, test counts,
and mutation-proof results. MiMo's own .agents/mimo/VERDICT-* is a self-report, not evidence.

Build request: .agents/requests/BUILD-rag-kg-round8.md
Previous checker verdict (what had to be fixed): .agents/deepseek/VERDICT-rag-kg-round7.md
Commits to check: f6c6ad4..HEAD
For EVERY item in the build request: verify it is done (file:line), and re-run each requested mutation proof yourself in /tmp —
the named test must FAIL on the mutated copy. Check no test was deleted or weakened: git diff f6c6ad4..HEAD -- tests.
Run: python -m pytest tests/rag -q and pyspark hidden (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps). Key: test (b) asserts validate index < first write index in ONE call list; schema test checks dataType + nullable per field incl. MapType valueContainsNull.
