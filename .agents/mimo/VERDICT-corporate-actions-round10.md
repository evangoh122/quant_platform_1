# VERDICT: corporate-actions-round10 — MiMo
**Status:** APPROVED
**Round:** 10

## Summary
All 3 blocking findings from DeepSeek round 9 verdict addressed:
1. Refactored per-batch loop into importable `run_batch()` with injectable Writer/CheckpointStore/KeyVerifier
2. Fixed SUCCESS logic: `all(k in verified_keys for k in sym_keys)` replaces buggy `setdefault` pattern
3. Post-append verification uses DataFrame join (no SQL string interpolation)

## Counts
- `python3 -m pytest -q tests/bronze tests/silver tests/test_security.py` → **354 passed, 13 skipped, 0 failed** (24.92s)
- `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest -q tests/bronze tests/silver tests/test_security.py` → **344 passed, 23 skipped, 0 failed** (4.00s)
- `python3 -m pytest -q tests/bronze/test_corporate_actions.py` → **95 passed, 0 failed** (0.90s)

## Source-grep tests deleted (replaced by functional)
1. `TestCheckpointOrdering::test_success_checkpoint_after_append_not_before` — structural line-ordering grep
2. `TestCheckpointOrdering::test_success_checkpoint_after_key_verification` — structural line-ordering grep
3. `TestCheckpointOrdering::test_no_success_checkpoint_in_fetch_loop` — structural grep for SUCCESS in fetch loop

## New functional tests (14 tests in TestRunBatchFunctional)
1. `test_crash_on_write_no_success_recorded` — writer raises → no SUCCESS checkpoint
2. `test_resume_after_crash_symbol_not_skipped` — same run_id re-fetches after crash
3. `test_truly_succeeded_symbol_is_skipped_on_resume` — SUCCESS symbol in completed_keys
4. `test_all_keys_verified_not_any` — 2 rows, 1 verified → FAILED (not SUCCESS)
5. `test_all_keys_verified_marks_success` — 2 rows, both verified → SUCCESS
6. `test_resume_with_partial_verification_retries` — FAILED verification → re-fetch on resume
7. `test_quote_in_symbol_handled_by_join` — symbol with quote verified correctly
8. `test_dry_run_skips_write_and_checkpoint` — dry-run mode: no writes/checkpoints
9. `test_existing_keys_anti_join` — existing keys filtered out
10. `test_failed_fetch_logged_and_continues` — FAILED fetch logged, other symbols continue

## Mutation proofs (3 tests in TestRunBatchMutationProofs)
1. `test_mutation_success_before_append_fails` — SUCCESS before append → FAILS (writer crash leaves SUCCESS)
2. `test_mutation_any_key_verified_fails` — ANY-key-verified logic → FAILS (partial verification allows SUCCESS)
3. `test_mutation_sql_interpolation_fails` — quote in symbol via join path works (no SQL interpolation)

## Key changes
- `notebooks/refresh_bronze_corporate_actions.py`: +120 lines (interfaces + run_batch), -120 lines (inline loop)
  - New classes: `Writer`, `CheckpointStore`, `KeyVerifier`, `SparkWriter`, `SparkCheckpointStore`, `SparkKeyVerifier`
  - New function: `run_batch()` — fully testable with in-memory fakes
  - `main()` now delegates to `run_batch()` via Spark implementations
- `tests/bronze/test_corporate_actions.py`: +316 lines (functional + mutation tests), -107 lines (structural tests)

## Checks run
- `python3 -m pytest -q tests/bronze tests/silver tests/test_security.py` → pass (354/13)
- `PYTHONPATH=.../nps python3 -m pytest -q tests/bronze tests/silver tests/test_security.py` → pass (344/23)
- `python3 -m pytest -q tests/bronze/test_corporate_actions.py` → pass (95)