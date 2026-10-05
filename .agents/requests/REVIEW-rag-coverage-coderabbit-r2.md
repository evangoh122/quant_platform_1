# REVIEW: rag-coverage — CodeRabbit PR #28 round 2 fixes (reviewer: Codex)

CodeRabbit's 9 findings: .agents/coderabbit-pr28-round2.md. Fixes ca64736 (MiMo), tests 5ef5687 (MiMo), and the latest commit (Claude tiny fix:
the discovery-CIK test now uses a filing-agent accession prefix outside the CIK group, parametrized over both members; reverting
`plan_cik = discovery_cik or next(iter(ticker_ciks))` fails it under PYTHONHASHSEED 1/2/3).
DeepSeek: r2 CHANGES_REQUESTED only for that test, r2b APPROVED (.agents/deepseek/VERDICT-rag-coverage-coderabbit-r2b.md). Earlier: (.agents/deepseek/VERDICT-rag-coverage-coderabbit-r2.md); the other 5 reverts each fail their test;
MiMo's "not valid" on api/main.py:305 judged defensible. Claude: tests/rag/test_sec_rag_ingest.py → 203 passed.
Run `python3 -m pytest tests/rag tests/api -q` (Databricks/warehouse calls are faked; a hang on SDK retries is a sandbox limit). Mutation proofs
only in /tmp via `git archive HEAD | tar -x -C /tmp/<dir>`. Judge each CodeRabbit finding: fixed correctly, or correctly rejected. The MAJOR one
(single-accession, parameterized lookup instead of a full-table read per filing) matters most. Print the verdict between ===VERDICT START=== /
===VERDICT END=== with "Status: APPROVED" or "Status: CHANGES_REQUESTED" and file:line. Do not edit files.
