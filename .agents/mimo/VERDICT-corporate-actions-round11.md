# VERDICT: corporate-actions-round11 — MiMo
**Status:** APPROVED
**Round:** 11

## Blocking findings
- None.

## Non-blocking notes
- Fix changes `run_batch()` verification from checking only `new_keys_set` to checking all `all_candidate_keys`. This means symbols with a mix of new + existing keys now verify all keys (not just new ones), which is stricter but correct.
- True conflicts (same key, different ratio) are still filtered by the anti-join into `conflicts` list and reported in `report["conflict_rows"]`. They are NOT silently marked SUCCESS — the anti-join prevents writing them, and the all-candidate-key verification confirms they exist in bronze.

## Rule implemented
Verify ALL fetched candidate keys for a symbol — new AND already-existing (conflict) keys — and record SUCCESS when every key is present in bronze, even when `new_rows` is empty. Keep true conflicts (same key, different ratio) reported as `conflict_rows` in the report (not silently SUCCESS).

## Checks run
- `PYTHONPATH=.../nps python3 -m pytest -q tests/bronze tests/silver tests/test_security.py` → 349 passed, 23 skipped (pyspark hidden)