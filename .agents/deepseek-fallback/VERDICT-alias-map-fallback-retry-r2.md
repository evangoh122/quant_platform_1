# Checker: Codex gpt-5.6-luna (DeepSeek out of balance) — alias-map r2 (saved by Claude)

===VERDICT START===
Status: CHANGES_REQUESTED

api/services/hybrid_retriever.py:804,830 — `_alias_map_loading` is not declared global in `reload_corpus()`, so invalidation fails to reset the module-level flag.

All required mutations failed; baseline tests passed (26). Worktree unchanged.
===VERDICT END===
