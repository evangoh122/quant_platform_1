# BUILD: alias-map fallback retry round 3 (checker CHANGES_REQUESTED — concurrent reloads)

You are MiMo. Branch `fix/alias-map-fallback-retry` (stay on it). Read `.agents/deepseek-fallback/VERDICT-alias-map-fallback-retry.md`. LF endings, never touch `.agents/dispatch.sh`, no Databricks,
no network. Shell rule as before (`/home/jianj/code/qp1-aliasfix/.agentlogs/<name>.sh` + `wsl -d Ubuntu -- bash <path>`; no PowerShell, nothing in C:\temp). Stage only files you change.
COMMIT; verdict `.agents/mimo/VERDICT-alias-map-fallback-retry-r3.md` with FAILED output. Tests may only call production code; never copy its logic.
api/services/hybrid_retriever.py:476-485 releases the lock before the reload, so after the retry deadline several callers reload at once (checker saw 2 warehouse reads). Make exactly ONE caller
reload: e.g. under the lock, if the deadline has passed and no load is in flight, set an `_alias_map_loading` flag (or push the deadline forward) before releasing the lock; other callers return
the current map without reading. Clear the flag in a finally. Test: N threads (≥4) call _load_alias_map() concurrently right after the deadline with a fake reader that blocks on an Event until
all threads have entered → exactly one read. Mutation: remove the in-flight guard → the test fails (paste FAILED output).
