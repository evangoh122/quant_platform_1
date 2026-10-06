# BUILD: alias-map fallback must not be cached forever (CodeRabbit follow-up from merged PR #43)

You are MiMo. Branch `fix/alias-map-fallback-retry` (worktree qp1-aliasfix, off main; stay on it). LF endings, never touch `.agents/dispatch.sh`, no Databricks, no network.
Shell rule: if quoting is hard, write to `/home/jianj/code/qp1-aliasfix/.agentlogs/<name>.sh` and run `wsl -d Ubuntu -- bash /home/jianj/code/qp1-aliasfix/.agentlogs/<name>.sh`.
No .ps1/.bat, no PowerShell wrappers, nothing in C:\temp. Stage only files you change. COMMIT; verdict `.agents/mimo/VERDICT-alias-map-fallback-retry.md` with FAILED output for each mutation
(mutate in a /tmp `git archive` copy). Tests may only call production code (`_load_alias_map`, `check_ticker_coverage`, …) with a fake warehouse/Spark; never copy its logic.
CodeRabbit (PR #43, api/services/hybrid_retriever.py:518-531): when gold_sec_coverage lacks `canonical_ticker` (or the load fails), `_load_alias_map` caches an empty identity map with
`_alias_map_loaded = True` for the whole process, so after the table is rebuilt an alias like GOOGL keeps resolving to itself → NoCoverageError until restart.
Fix: on the missing-column or failure fallbacks, return the identity map but do NOT mark it permanently loaded — record a retry deadline (e.g. `_alias_map_retry_at = time.monotonic() + 300`;
make the interval a module constant) and reload on the first call after it. A successful load is still cached permanently (existing reload_corpus() invalidation unchanged). Thread-safe
under the existing lock; no thundering herd (only one caller reloads after the deadline).
Tests: (1) first load sees no canonical_ticker → identity; advance the clock past the interval (monkeypatch time.monotonic) with a fake now returning canonical rows → GOOGL resolves to
GOOGL's canonical; (2) before the deadline no reload happens (fake reader called once); (3) a successful load is never re-read. Mutations: set `_alias_map_loaded = True` on fallback → (1)
fails; drop the deadline check (reload every call) → (2) fails.
