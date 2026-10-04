# REVIEW: ontology update (reviewer: dataexpert Claude — replaces the Codex review step, owner rule 2026-10-04)

You are the independent REVIEWER, after the checker. Read-only for source: do NOT edit ontology/ or tests/ or any code.
Scratch work and mutation proofs go under /tmp only (cp -r the repo to /tmp/onto-review-*).

Scope: branch slice/ontology-update vs origin/main (`git diff origin/main...HEAD -- ontology tests/test_ontology.py tests/fixtures`).
Context: .agents/requests/BUILD-ontology-update-round6.md, -round7.md; Codex reports .agents/codex/REPORT-ontology-round6.md, -round7.md;
checker verdicts .agents/deepseek/VERDICT-ontology-update-check5.md and -check6.md. Other lanes are local branches:
read with `git show <branch>:<path>` (slice/corporate-actions, slice/nl-contracts, slice/rag-coverage, slice/rag-kg).

Review for:
1. Factual correctness: pick at least 10 table/metric/join claims (favour ones the checker did NOT cite) and verify each against code.
2. Point-in-time safety of every join hint; any place a business date stands in for availability.
3. Internal consistency: every reference resolves; no duplicate/conflicting business terms or aliases; statuses/enums match code.
4. Test quality: do tests/test_ontology.py tests actually fail on realistic errors? Run at least 3 mutation proofs of your own
   choosing (different from the checker's) in /tmp copies.
5. Known, accepted follow-up (NOT a blocker): corporate-actions section is stale vs that lane's in-progress Massive work.
Run: python3 -m pytest tests/test_ontology.py -q -rs

Output ONLY to stdout, between lines `===VERDICT START===` and `===VERDICT END===`: first line "Reviewer: dataexpert Claude (claude-sonnet-5-5)",
then "Status: APPROVED" or "Status: CHANGES_REQUESTED", then numbered findings with file:line evidence, test counts, mutation results.
