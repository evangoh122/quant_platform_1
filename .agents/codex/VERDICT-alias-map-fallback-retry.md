# Codex gpt-5.6-sol review — alias-map fallback retry (saved by Claude)

===VERDICT START===
Status: APPROVED

api/services/hybrid_retriever.py:477-557 — fallback retries are deadline-gated, concurrent reloads are coalesced, and successful loads remain permanently cached.

api/services/hybrid_retriever.py:804-831 — full reload correctly resets all alias-map state, including `_alias_map_loading`.

tests/api/test_hybrid_retriever.py:854-1058,1094-1353 — coverage exercises all fallback branches, concurrency, permanent success caching, and full reset.

Validation:
- Required suite: 181 passed.
- `/tmp` cache-forever mutation: correctly failed.
- `/tmp` in-flight-guard removal: correctly failed with 6 warehouse reads.
- `/tmp` missing-global mutation: correctly failed.
- Worktree remained clean.
===VERDICT END===
