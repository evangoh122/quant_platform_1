# REVIEW: alias-map fallback retry — follow-up to merged PR #43 (reviewer: Codex sol)

Branch fix/alias-map-fallback-retry (off main). CodeRabbit (PR #43): the missing-canonical_ticker fallback cached an empty alias map for the process lifetime. Fixes: dade365 (retry deadline
instead of cache-forever, all three fallback branches), 806bb45 (tests per branch), d2bb78c (single in-flight reload guard), latest commit (Claude tiny fix: `_alias_map_loading` declared global
in reload_corpus + test). Checker luna: r1 CHANGES_REQUESTED (concurrent reloads) → r2 CHANGES_REQUESTED (global missing) → fixed by the latest commit (tiny, test-backed).
Claude: 148 passed; mutations — cache-forever (missing-column branch), removing the in-flight guard, dropping the global — each fail a test.
Run `python3 -m pytest tests/api/test_hybrid_retriever.py tests/rag/test_hybrid_retriever.py tests/gold -q`. Mutation proofs only in /tmp via `git archive HEAD`. Judge correctness, thread safety,
and that a successful load is still cached permanently. Print the verdict between ===VERDICT START=== / ===VERDICT END=== with "Status: APPROVED" or "Status: CHANGES_REQUESTED" and file:line.
Do not edit files.
