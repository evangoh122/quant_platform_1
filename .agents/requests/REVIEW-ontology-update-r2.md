# RE-REVIEW: ontology update after round 8 (reviewer: dataexpert Claude)

Read-only for the repo; scratch and mutation copies under /tmp only. Your previous verdict:
.agents/reviewer/VERDICT-ontology-update-review1.md. Round 8 request: .agents/requests/BUILD-ontology-update-round8.md
(includes a NEW item 8: options `right` mixed case + implied_volatility snapshot-only caveat, found live by Claude).
Round 8 = the latest "fix(ontology): round 8" commit (git show HEAD~0 / git log).
1. Verify each of your 7 findings is fixed correctly (file:line), and item 8 is accurately worded.
2. Re-run your mutations M-C, M-D, M-E — each must now FAIL — and run 2 NEW mutations of your choice targeting the new tests.
3. Check the new tests are not over-fitted (e.g. the PIT-direction check doesn't pass vacuously because it matches nothing:
   confirm it actually iterates over the real join conditions; count how many conditions it checks).
4. Anything new the round introduced that is false against code.
Run: python3 -m pytest tests/test_ontology.py -q -rs
Output ONLY between `===VERDICT START===` and `===VERDICT END===`: "Reviewer: dataexpert Claude (claude-sonnet-5-5)",
"Status: APPROVED" or "Status: CHANGES_REQUESTED", numbered findings with file:line, counts, mutation results.
