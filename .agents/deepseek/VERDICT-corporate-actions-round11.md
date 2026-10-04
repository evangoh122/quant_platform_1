===VERDICT START===
# VERDICT: corporate-actions-round11 — DeepSeek (checker)
**Status: APPROVED**
**Round:** 11
Scope: commit 4ef30e2 (MiMo's fix — `run_batch()` verifies ALL candidate keys on resume so all-conflict symbols get a SUCCESS checkpoint). Read-only review; mutation proof in `/tmp/corpact-mut` via `git archive HEAD | tar -x -C`.

## Verified OK — the Codex review3 blocker is fixed

### 1. Resume with all keys already in bronze now records SUCCESS.
`notebooks/refresh_bronze_corporate_actions.py:388-417` moved verification OUT of the `if mode == "write" and new_rows:` block and gated it on `if mode == "write" and successful_symbols:`. It now verifies `all_candidate_keys` (new + conflict keys) via `key_verifier.verify_keys(...)`, groups `all_candidate_rows` by symbol, and records `SUCCESS` when `all(k in verified_keys for k in sym_keys)`. On the Codex probe (existing_keys_set = all SYM keys, no prior SUCCESS) this yields `SUCCESS`, writer not called, verifier called; a second resume skips SYM. Confirmed by `test_resume_all_keys_already_in_bronze_records_success` and `test_resume_skips_already_bronze_symbol`.

### 2. True-conflict rule stated and preserved (not silently SUCCESS).
The natural key is `(symbol, ex_date, source)` — ratio is deliberately excluded (`_row_to_key`, line 137-139). The anti-join at 369-370 still splits candidates into `new_rows` vs `conflicts`, and `report["conflict_rows"] = len(conflicts)` is surfaced in the printed/JSON report. So a "same key, different ratio" row is never written (writer skips it) and is still counted in `conflict_rows`; the SUCCESS checkpoint reflects only "all of this symbol's keys are present in bronze" (idempotency/resume), not a claim that the ratio matched. Rule stated in the code comment (388-392) and commit message. Existing tests `test_same_key_different_ratio_is_conflict` and the `conflict_rows == 1` assertion (line 1637) still pass.

### 3. Earlier fixes still hold (spot-checked, all passing).
- ALL-key (not ANY-key) verification: `all(k in verified_keys ...)` at line 409; `test_all_keys_verified_not_any`.
- SUCCESS after append: write block (375-386) precedes verification/SUCCESS (388-417); `test_crash_on_write_no_success_recorded`.
- Adapter delay: `_make_adapter` forwards `delay_seconds`/`max_retries`; `MassiveCorporateActionsSource` enforces `self._sleeper(self._delay)` (etl/corporate_actions.py:213,228,241).
- Key decode: `_resolve_cli_api_key()` (95-111) still base64-decodes the SDK secret and leaves env keys verbatim.

### 4. No tests deleted/weakened.
`git show 4ef30e2 --stat`: `tests/bronze/test_corporate_actions.py` +152 (insertions only, 0 deletions); `notebooks/refresh_bronze_corporate_actions.py` +11/-6 (refactor of the verification block, no semantics removed).

### 5. Mutation proof: reverting to "verify only new rows" breaks the tests.
In `/tmp/corpact-mut` I changed the gate to `if mode == "write" and new_rows:`, verified `new_keys_set = {_row_to_key(r) for r in new_rows}`, and grouped `new_rows`. Result: all three round-11 tests FAIL:
```
FAILED ...::TestRunBatchMutationProofs::test_resume_all_keys_already_in_bronze_records_success
FAILED ...::TestRunBatchMutationProofs::test_resume_skips_already_bronze_symbol
FAILED ...::TestRunBatchMutationProofs::test_mutation_verify_only_new_rows_fails
3 failed, 97 deselected
```
`test_mutation_verify_only_new_rows_fails` asserts `len(success_logs) == 1` and fails with `assert 0 == 1` ("Mutation detected: only new_rows were verified..."), proving the test is load-bearing against the exact defect.

## Blocking findings
None.

## Non-blocking notes
1. **[notebooks/refresh_bronze_corporate_actions.py:393-395] verification now runs on every write-mode batch even when `new_rows` is empty**, adding one DataFrame join per batch. Bounded by candidate rows per batch, not the whole bronze table — negligible cost, correctness wins.
2. **[notebooks/refresh_bronze_corporate_actions.py:395] `all_candidate_keys` re-derives keys from `all_candidate_rows`**; a symbol could in principle be double-counted across a symbol already present in `completed_keys`, but those are skipped at line 320, so `successful_symbols` and `all_candidate_rows` stay consistent.
3. True conflicts (ratio changed) are reported but still never reconciled (first-write-wins, append-only bronze). This is the pre-existing design contract, not introduced here; `conflict_rows` is the operator-facing alert.

## Checks run
- `python3 -m pytest -q tests/bronze tests/silver tests/test_security.py` → **359 passed, 13 skipped, 0 failed** (34.71s). All 13 skips are the pre-existing "db.database (DuckDB) removed; Delta is the store" markers.
- `python3 -m pytest -q tests/bronze/test_corporate_actions.py -k "resume_all_keys_already_in_bronze_records_success or resume_skips_already_bronze_symbol or mutation_verify_only_new_rows_fails"` → **3 passed**.
- Mutation (verify only new rows) in `/tmp/corpact-mut` → **3 failed** (see §5).
- `git status --porcelain` in the WSL worktree → clean (no repository files modified by this review).
===VERDICT END===
