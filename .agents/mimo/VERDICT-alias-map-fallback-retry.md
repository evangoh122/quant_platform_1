# VERDICT: alias-map-fallback-retry — MiMo
**Status:** APPROVED
**Round:** 1

## Blocking findings
- None.

## Non-blocking notes
- The `_ALIAS_MAP_RETRY_INTERVAL` (300s) is a module constant, easily tunable.
- The retry deadline check is inside `_alias_map_lock` so only one thread retries after the deadline (no thundering herd).
- Empty rows (no data yet) also use the retry deadline rather than permanent caching — consistent with the failure paths.
- Updated existing `TestStartupWarmupMissingTable` assertion to check `_alias_map_loaded is False` + `_alias_map_retry_at > 0` (was checking `_alias_map_loaded is True`).

## Checks run
- `python3 -m pytest tests/api/test_hybrid_retriever.py -v` → 21/21 passed
- `python3 -m pytest tests/rag/test_hybrid_retriever.py -v -k alias` → 6/6 passed
- **Mutation 1:** set `_alias_map_loaded = True` on fallback → `test_fallback_then_retry_loads_canonical` FAILS (`assert True is False` at :749)
- **Mutation 2:** drop deadline check (reload every call) → `test_no_reload_before_deadline` FAILS (`Expected 1 read, got 6`)