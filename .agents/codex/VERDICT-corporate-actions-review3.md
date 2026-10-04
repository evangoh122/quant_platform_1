===VERDICT START===

# VERDICT: corporate-actions-r3

Status: CHANGES_REQUESTED

DeepSeek prerequisite: round 10b is APPROVED.

## Blocking finding

1. Resume cannot reconcile rows committed before a missing SUCCESS checkpoint.

   At `notebooks/refresh_bronze_corporate_actions.py:368-375`, existing Bronze rows are removed by the anti-join, and verification/checkpointing only runs when `new_rows` is non-empty. If Bronze append commits but execution stops before SUCCESS is recorded, the next run loads those keys at lines 623-630, re-fetches the symbol, classifies every row as a conflict, and performs neither verification nor checkpointing.

   Independent probe representing this state produced:

   `fetched=['SYM'], writer_calls=0, verifier_calls=0, checkpoint_logs=[], conflicts=1`

   Every subsequent resume with that run ID repeats the fetch. Verification should cover all fetched candidate keys—including existing conflicts—and record SUCCESS when all are present. Add a regression test with a populated `existing_keys_set` and no prior SUCCESS checkpoint.

## Verified fixes

- Job and runbook use `source=massive`.
- Empty responses and pagination are rate-limited inside the adapter.
- SUCCESS is not recorded before append.
- ALL-key verification uses `all(...)`, not ANY-key semantics.
- The real `SparkKeyVerifier` uses an inner DataFrame join on `(symbol, ex_date, source)`; a quote-bearing symbol was verified without appearing in SQL.
- `_resolve_cli_api_key()` decodes SDK secrets while leaving environment-provided keys unchanged.

## Verification

- Required suite: `349 passed, 20 skipped` in 307.77 seconds.
- Focused probes: `17 passed, 80 deselected`.
- Mutations in separate `git archive HEAD` copies:
  - Massive → yfinance wiring: 2 expected failures.
  - Removed adapter delay: 3 expected failures.
  - SUCCESS before append: 3 expected failures.
  - `all(...)` → `any(...)`: 2 expected failures.
  - Removed SDK-secret decoding: 1 expected failure.
- Repository remained clean; no repository files were modified.

===VERDICT END===
