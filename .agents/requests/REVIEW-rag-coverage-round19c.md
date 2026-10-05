# REVIEW: rag-coverage rounds 19 + 19b + 19c (reviewer: Codex)

Branch slice/rag-coverage (PR #28). Commits since your last review: d7f7b89 CIK overrides, c43d5a8 foreign filers (20-F/40-F/6-K),
5aa58dd runbook/xbrl resolver, d1134e2 ownership group (19b), and the 19c commit (override-group filings fetched/stored under the
accession filer CIK; deduped counters; parameterized repair_cik_ownership). DeepSeek: round 19 CHANGES_REQUESTED → 19c APPROVED
(.agents/deepseek/VERDICT-rag-coverage-round19c.md, 4 mutations killed). Claude: tests/rag + tests/bronze → 1177 passed.
Your sandbox has no network: run `python3 -m pytest tests/rag tests/bronze -q`. Mutation proofs only in /tmp copies via
`git archive HEAD | tar -x -C /tmp/<dir>`. Focus: point-in-time correctness of stored filings, SQL safety, foreign-filer section parsing
not breaking 10-K/10-Q, default forms unchanged (10-K,10-Q). Print the verdict to stdout between ===VERDICT START=== / ===VERDICT END===
with "Status: APPROVED" or "Status: CHANGES_REQUESTED" and file:line. Do not edit files.
