# REVIEW: share-class canonical ticker — GOOGL/GOOG coverage (reviewer: Codex sol)

Branch fix/sec-silver-share-class (off main). Bug: gold/07_gold_sec_coverage.sql and api/services/hybrid_retriever.py `_load_alias_map` chose the
canonical ticker per CIK alphabetically (GOOG) while the chunks are stored under GOOGL → both reported 0 chunks and the agent answered no_coverage.
Fix: canonical = ticker with the most chunks (tie → alphabetical) in both places. Commits e0defee, 6584cb3, 635c321. Checker (Codex luna, DeepSeek out of
balance) APPROVED: .agents/deepseek-fallback/VERDICT-sec-share-class.md. Claude: 269 passed; read-only live SELECT of the new 07 → GOOG 831, GOOGL 831,
230 covered tickers (was 228).
Run `python3 -m pytest tests/gold tests/silver tests/api/test_hybrid_retriever.py tests/rag/test_hybrid_retriever.py -q`. Mutation proofs only in /tmp via
`git archive HEAD`. Judge: SQL and alias map always agree; no regression for single-ticker CIKs and other share classes (BRK.A/BRK.B: BRK.A has no mapped
CIK — acceptable?); SQL has no user input. Print the verdict between ===VERDICT START=== / ===VERDICT END=== with "Status: APPROVED" or
"Status: CHANGES_REQUESTED" and file:line. Do not edit files.
