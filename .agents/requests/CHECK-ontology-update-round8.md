# CHECK: ontology-update-round8 (checker: DeepSeek)

Read-only for source: do NOT edit code or tests. Mutation proofs go in /tmp copies (cp -r the repo to /tmp/ontology-update-round8-mut-*).
Write your verdict to .agents/deepseek/VERDICT-ontology-update-round8.md between ===VERDICT START=== and ===VERDICT END===,
with "Status: APPROVED" or "Status: CHANGES_REQUESTED", numbered findings with file:line evidence, test counts,
and mutation-proof results. MiMo's own .agents/mimo/VERDICT-* is a self-report, not evidence.

Build request: .agents/requests/BUILD-ontology-update-round8.md (author was Codex)
Previous checker verdict (what had to be fixed): .agents/deepseek/../reviewer/VERDICT-ontology-update-review1.md (dataexpert Claude review)
Commits to check: the 'fix(ontology): round 8' commit vs its parent
For EVERY item in the build request: verify it is done (file:line), and re-run each requested mutation proof yourself in /tmp —
the named test must FAIL on the mutated copy. Check no test was deleted or weakened: git diff the 'fix(ontology): round 8' commit vs its parent -- tests.
Factual correctness against code is the job: other lanes are local branches, read with git show <branch>:<path>. Verify all 7 review findings + item 8 (options right mixed case; implied_volatility snapshot-only). Re-run the review's mutations M-C (duplicate aliases), M-D (deterministic_counts), M-E (flip <= to >= in join conditions) — each must now fail — and confirm the PIT-direction test iterates over the real join conditions (count them). Run: python3 -m pytest tests/test_ontology.py -q -rs
