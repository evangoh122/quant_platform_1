# BUILD: alias-map fallback retry round 2 — the key mutation survives (Claude spot check)

You are MiMo. Branch `fix/alias-map-fallback-retry` (stay on it). LF endings, never touch `.agents/dispatch.sh`, no Databricks, no network. Shell rule as before
(`/home/jianj/code/qp1-aliasfix/.agentlogs/<name>.sh` + `wsl -d Ubuntu -- bash <path>`; no PowerShell, nothing in C:\temp). Stage only files you change. COMMIT; verdict
`.agents/mimo/VERDICT-alias-map-fallback-retry-r2.md` with FAILED output. Tests may only call production code; never copy its logic.
Claude mutated api/services/hybrid_retriever.py's MISSING-COLUMN branch (the `if "UNRESOLVED_COLUMN" in msg or (...)` block) back to `_alias_map = {}; _alias_map_loaded = True` (cache forever)
→ all 142 tests still pass. Your tests do not drive that branch (they probably hit the `if not rows` or generic-exception path).
Add tests that drive EACH fallback path through the production `_load_alias_map()` with a fake warehouse/Spark: (a) the read raises an exception whose message contains
`[UNRESOLVED_COLUMN.WITH_SUGGESTION] ... canonical_ticker` (the real Databricks text); (b) the read returns no rows; (c) a generic exception. For each: identity map now; before the deadline no
re-read; after advancing time.monotonic past the deadline with a reader that now returns canonical rows → GOOG resolves to GOOGL. Paste FAILED output for the cache-forever mutation on each
of the three branches.
