===VERDICT START===
# VERDICT: corporate-actions-round12 — DeepSeek (checker)
**Status: APPROVED**
**Round:** 12
Scope: commit 7cdad50 (MiMo's DuckDB adjusted-arithmetic tests + runbook conflict docs) plus commit 9b96b34 (Claude's notebook header + guard test). Read-only review; mutation proofs in `/tmp/mutA`, `/tmp/mutB`, `/tmp/mutC` via `git archive HEAD | tar -x -C`.

## Verified OK — the three round-12 asks are satisfied

### 1. DuckDB tests extract `_adjusted` (and its CTEs) from silver/08 at test time and RUN — mutations FAIL.
`tests/silver/test_silver_sql_semantics.py` new block (§8, `TestAdjustedArithmetic` + `_run_adjusted`/`adjusted_conn`). `_run_adjusted` pulls the real SQL via `_extract_cte(sql_text, "_massive_splits" | "_split_factors" | "_adjusted")` where `sql_text` is `silver/08_silver_ohlcv_day_adjusted.sql` read verbatim, shims the schema prefix, and executes `_massive_splits` → `_split_factors` → `_adjusted` in DuckDB. It does NOT re-implement the arithmetic in Python — it asserts the exact values the real view computes.
- Two-split cumulative product (`TWOSPLIT`: two 2:1) — cum 4/2/1, adj_close 100/50/55, adj_volume 4M/6M/6M asserted exactly.
- Reverse split (`REV`: 0.1) — cum 0.1 → 1, adj_close 5/0.1=50, adj_volume 500K*0.1=50K asserted exactly.
- Ex-date bar on new basis (`EXDATE`: 3:1) — cum 3 before, 1 on ex-date; adj_close 100 before / 105 on ex-date, adj_volume 1.2M unchanged on ex-date asserted.
The 21 tests in this file pass (duckdb 1.5.6 installed) — none skip.

Mutation A (adj_close = close * cum): `sed -i '199s|…|dd.close * COALESCE(sf.cumulative_split_ratio, 1.0) AS adj_close,|'` → **5 failed, 16 passed** (`test_two_split_cumulative_product`, `test_reverse_split_exact_values`, `test_exdate_bar_on_new_basis`, `test_mutation_adj_close_times_cum_fails`, `test_reverse_split_mutation_adj_close`).

Mutation B (adj_volume = volume / cum): `sed -i '204s|…|dd.volume / NULLIF(COALESCE(sf.cumulative_split_ratio, 1.0), 0) AS adj_volume,|'` → **5 failed, 16 passed** (`test_two_split_cumulative_product`, `test_reverse_split_exact_values`, `test_exdate_bar_on_new_basis`, `test_mutation_adj_volume_div_cum_fails`, `test_reverse_split_mutation_adj_volume`).

Both reviewer-surviving mutations now die on the ex-date-bar / exact-value assertions, not just on the `!=` mutation-proof asserts.

### 2. Notebook header guard test is load-bearing.
`test_notebook_task_targets_have_databricks_header` (tests/bronze/test_corporate_actions.py) reads `resources/jobs.yml`, resolves every `notebook_task.notebook_path`, and asserts line 1 is `# Databricks notebook source`. Mutation C (delete the header line from `notebooks/refresh_bronze_corporate_actions.py`) → **1 failed**: `AssertionError: /tmp/mutC/notebooks/refresh_bronze_corporate_actions.py is a notebook_task target without the header`. Header fix itself confirmed at line 1 of the notebook.

### 3. Runbook + WARNING log.
`docs/CORPORATE_ACTIONS_RUNBOOK.md` now documents: job defaults to `--mode dry-run` with no schedule; write mode via `--mode write`; first-write-wins on `(symbol, ex_date, source)`; `conflict_rows` surfaced in the JSON report; and "Rerun once — prove zero appended rows (conflict_rows should equal total)". `notebooks/refresh_bronze_corporate_actions.py:375-379` emits `WARNING: N conflict(s) detected — … First-write-wins: conflicts are NOT overwritten. Investigate…` when `report["conflict_rows"] > 0`.

## Blocking findings
None.

## Non-blocking notes
1. **[notebooks/refresh_bronze_corporate_actions.py:375] WARNING fires in dry-run too**, i.e. on any run where incoming keys already exist — including the deliberate "rerun once" idempotency probe. That is consistent with the runbook's "investigate" guidance and is informational only, but operators should expect the warning on a correct no-op rerun, not only on true ratio conflicts.
2. **[tests/silver/test_silver_sql_semantics.py] the `!=` mutation-proof asserts** (`adj_close != pytest.approx(close * cum)` etc.) are strictly weaker than the exact-value asserts and would not catch a mutation that coincidentally matches on the chosen fixture; the real guard is the exact-value assertions, which is where both mutations actually failed. Fine as belt-and-suspenders.
3. **[tests/silver/test_silver_sql_semantics.py:684] `_run_adjusted` executes `_adjusted` after `_split_factors` in one DuckDB session**, so the extracted views compose correctly only because the shim strips the `bootcamp_students.evangoh_capstone.` prefix and `_deduped_daily`/`_universe`/`bronze_corporate_actions` are pre-created by `_setup_duckdb`/`adjusted_conn`. This is test-infrastructure coupling, not a correctness issue.

## No tests deleted/weakened
`git show 7cdad50 --stat`: `tests/silver/test_silver_sql_semantics.py` +222/-0 (additions only), `notebooks/refresh_bronze_corporate_actions.py` +6, `docs/CORPORATE_ACTIONS_RUNBOOK.md` +21/-3. `git show 9b96b34 --stat`: `notebooks/…` +1, `tests/bronze/test_corporate_actions.py` +21. No deletions anywhere.

## Checks run
- `python3 -m pytest -q tests/bronze tests/silver tests/test_security.py -rs` → **367 passed, 13 skipped, 0 failed** (20.84s). All 13 skips are the pre-existing "db.database (DuckDB) removed; Delta is the store" / "rag_engine (DuckDB vector retriever) removed" markers — none from the new DuckDB block.
- `python3 -m pytest -q tests/silver/test_silver_sql_semantics.py` → **21 passed** (duckdb 1.5.6, no skips).
- Mutation A (adj_close = close * cum) in `/tmp/mutA` → **5 failed, 16 passed**.
- Mutation B (adj_volume = volume / cum) in `/tmp/mutB` → **5 failed, 16 passed**.
- Mutation C (notebook header removed) in `/tmp/mutC` → **1 failed** (`test_notebook_task_targets_have_databricks_header`).
- `git status --porcelain` in the WSL worktree → clean; branch `slice/corporate-actions`; HEAD not on `main`.
===VERDICT END===
