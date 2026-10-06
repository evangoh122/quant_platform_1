# VERDICT: alias-map-fallback-retry-r3 — MiMo
**Status:** APPROVED
**Round:** 3

## Blocking findings
- None.

## Non-blocking notes
- The `_alias_map_loading` flag is set under the lock before releasing it, so only one caller can enter the reload path. Other callers return the stale map immediately.
- The flag is cleared in a `finally` block so it is always reset even on exceptions (including early `return {}` inside the try block, since Python `finally` executes on all exit paths).
- `reload_corpus()` also resets `_alias_map_loading = False` to avoid stale state after full invalidation.
- The mutation test uses a standalone `_mutated_load()` function (not monkey-patching the production code) to safely demonstrate the failure mode without leaving the guard permanently removed.

## Checks run
```
python3 -m pytest tests/api/test_hybrid_retriever.py -xvs 2>&1
  26 passed in 0.96s

python3 -m pytest tests/rag/test_hybrid_retriever.py -x --tb=short 2>&1
  121 passed in 1.47s

python3 -m pytest tests/api/test_hybrid_retriever.py::TestConcurrentReloadGuard -xvs 2>&1
  2 passed in 0.84s

# Mutation proof (guard removed): standalone script
python3 .agentlogs/mimo_mutation.py 2>&1
  read_count = 6
  FAILED: Multiple callers reloaded concurrently (guard removed -> read_count > 1)
```

## Files changed
- `api/services/hybrid_retriever.py` — added `_alias_map_loading` flag + in-flight guard in `_load_alias_map()` + reset in `reload_corpus()`
- `tests/api/test_hybrid_retriever.py` — added `TestConcurrentReloadGuard` (2 tests: guard-present and mutation-proof)

## Commit
`d2bb78c` on `fix/alias-map-fallback-retry` — `fix: prevent concurrent alias-map reloads after retry deadline`