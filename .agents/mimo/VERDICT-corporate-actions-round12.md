# VERDICT: corporate-actions-round12 — MiMo
**Status:** APPROVED
**Round:** 12

## Blocking findings
None.

## Non-blocking notes
- The `_adjusted` CTE extraction for DuckDB required no shim changes; existing `_setup_duckdb` base tables (`_deduped_daily`, `_universe`, `bronze_corporate_actions`) satisfy all dependencies.
- The mutation proofs (adj_close = close * cum, adj_volume = volume / cum) are structurally sound: the correct formula differs from the mutated one by a factor of cum², which is always != 1 for any non-trivial split.
- Runbook now documents first-write-wins conflict semantics and dry-run default mode.

## Checks run
- `PYTHONPATH=... python3 -m pytest -q tests/bronze tests/silver tests/test_security.py` → 357 passed, 23 skipped
- `git diff --stat` → 3 files changed, 246 insertions, 3 deletions
- Commit `7cdad50` on `slice/corporate-actions`

## What was delivered
1. **DuckDB adjusted-arithmetic tests** (`tests/silver/test_silver_sql_semantics.py`):
   - `TestAdjustedArithmetic` class with 7 tests
   - Fixture `adjusted_conn` with three scenarios: two-split (cumulative product), reverse split (0.1), ex-date bar on new basis
   - `test_two_split_cumulative_product`: exact adj_close and adj_volume for cum=4, cum=2, cum=1
   - `test_reverse_split_exact_values`: exact adj_close and adj_volume for cum=0.1
   - `test_exdate_bar_on_new_basis`: ex-date bar has cum=1 (adj_close = raw close)
   - `test_mutation_adj_close_times_cum_fails`: proves adj_close = close * cum is wrong
   - `test_mutation_adj_volume_div_cum_fails`: proves adj_volume = volume / cum is wrong
   - `test_reverse_split_mutation_adj_close`: reverse-split mutation proof
   - `test_reverse_split_mutation_adj_volume`: reverse-split mutation proof
2. **WARNING log** (`notebooks/refresh_bronze_corporate_actions.py:374-377`): emits warning when `conflict_rows > 0`
3. **Runbook update** (`docs/CORPORATE_ACTIONS_RUNBOOK.md`): documents first-write-wins, conflict_rows investigation, dry-run default, write-mode invocation