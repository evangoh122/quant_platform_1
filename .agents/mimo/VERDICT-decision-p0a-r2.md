# VERDICT: decision-p0a-r2 — MiMo
**Status:** APPROVED
**Round:** 2

Builder evidence for `.agents/requests/BUILD-decision-p0a-r2.md` (MiMo builder lane).
Base: request cites `aacee9c`; the tree at start was `e5d2b56` (= `aacee9c` +
`chore: route DeepSeek p0a findings to MiMo (round 2)`, which added the request
file). Fix commit: `c124a8d`. Harness-tweak commit: `0399078`. Mutation copies:
`git archive 0399078`. Branch: `feat/decision-dashboard-p0`. No deploy, no live
data, no new dependencies (duckdb/pyspark already in requirements).

## Site audit — unordered Spark limits (B1 + mandated audit)

| Site | Decision | Reason |
| :--- | :--- | :--- |
| `db/delta_adapter.py:457` `market_features` (PySpark) | **CHANGED** (B1) | Was `df.limit(limit)` with no order; warehouse `_build_market_features_daily_query` orders `event_date DESC`. Added `.orderBy(F.col("event_date").desc())` before `.limit`. |
| `db/delta_adapter.py:508` `read_analytics_table` (PySpark) | **CHANGED** | Reads bounded recent analytics rows; its warehouse fallback is `ORDER BY event_date DESC`. Added `orderBy(F.col("event_date").desc())` before `.limit`, same column the warehouse orders by. |
| `agent/tools_retrieval.py:442-445` `get_cot_positioning` (PySpark `.limit(1)`) | **CHANGED** | Mandate: "order them too, e.g. `get_cot_positioning`". Added `.orderBy(F.col("report_date").desc())` before `.limit(1)` (newest COT report deterministically). |
| `agent/tools_retrieval.py` `_build_cot_query` (warehouse SQL) | **CHANGED** | The warehouse variant did **not** previously order (the mandate's premise "unless the warehouse variant orders them" did not hold as written). Ordering only the Spark branch would recreate the exact B1 defect class (backends disagreeing on which row survives `.limit(1)`), so `ORDER BY report_date DESC` was added to the warehouse query too — both backends now return the same newest report. |
| `db/delta_adapter.py:401` `read_table` (PySpark) | **LEFT** | Generic DuckDB-shim table reader (`SELECT * FROM … [WHERE …]` + LIMIT on the warehouse side too). The matching warehouse query is **not** newest-first, so per the mandate ("add the same ordering … where the matching warehouse query is newest-first", "using the column the warehouse query orders by") there is no ordering to mirror; not a per-symbol time-series read. |
| `db/delta_adapter.py:475` `market_features_intraday` (PySpark) | **LEFT** (follow-up recommended) | Reads a time series (`feature_ts BETWEEN …`) but its matching warehouse query `_build_market_features_intraday_query` has **no** `ORDER BY` — the mandate conditions the fix on the warehouse being newest-first and sources the column from the warehouse order. Both backends are unordered today (no row-order disagreement). Residual nondeterminism flagged in non-blocking notes. |
| `db/delta_adapter.py:527` `read_analytics_cdc_state` (`.limit(1)`) | **LEFT** | Single-row state lookup; warehouse variant is `SELECT * … LIMIT 1` with no order → mandate says leave `.limit(1)` lookups alone unless the warehouse variant orders them. |
| `agent/tools_retrieval.py:115-117` `get_options_features` (PySpark) | **LEFT (already fixed)** | r1 fix stands: `orderBy(F.col("feature_ts").desc())` before `.limit`; warehouse `_build_options_query` orders `feature_ts DESC`. |
| `db/delta_adapter.py:428` `latest_signals` (PySpark) | **LEFT (already ordered)** | Both branches order `prediction_ts DESC` (incl. `get_latest_signal`'s `.limit(1)`). |

## Tests (one per changed site; real production function + recording Spark stub)

| Changed site | Test |
| :--- | :--- |
| `db.delta_adapter.market_features` | `tests/agent/test_delta_adapter_ordering.py::test_market_features_orders_event_date_desc_before_limit` |
| `db.delta_adapter.read_analytics_table` | `tests/agent/test_delta_adapter_ordering.py::test_read_analytics_table_orders_event_date_desc_before_limit` (+ `…_ordering_applies_to_all_sections` covering all 7 sections) |
| `agent.tools_retrieval.get_cot_positioning` | `tests/agent/test_tools_retrieval_ordering.py::test_cot_positioning_orders_report_date_desc_before_limit` |
| `agent.tools_retrieval._build_cot_query` (SQL builder — no Spark branch) | `tests/agent/test_tools_retrieval_ordering.py::test_cot_query_orders_report_date_desc` asserts the built SQL orders `report_date DESC` |

All Spark-site tests call the real production function with `_has_pyspark=True`
and stubbed `_spark()` (recording DataFrame), asserting `orderBy` with a
DESCENDING column of the right name happens **before** `limit`. No production
logic is copied into the tests.

## Other required fixes
- **M4 semantic kill:** `tests/gold/test_zscore_window_guard.py::_extract_zscore_expression`
  was locating the item by scanning back to the nearest line containing `CASE`,
  so a guard-less (CASE-free) item pulled in an unrelated earlier `CASE` from
  the `oi_conc` CTE and produced malformed SQL (duckdb `ParserException`).
  Replaced with a paren-depth-aware backward scan to the nearest top-level
  comma (the select-list item boundary). Verified: unmutated SQL extracts
  `CASE WHEN vw.vol_count >= 20 THEN … END`; the M4 mutation extracts
  `(day.total_volume - vw.avg_vol) / NULLIF(vw.std_vol, 0)` — SQL still parses,
  and M4 now fails on the NULL assertion (see transcript).
- **Harness honesty (`.agents/run-mutations.py`):** removed `--noconftest`
  (conftest now loads; `fake_lakebase` resolves — M2/M3 can no longer
  "fail" on a missing-fixture error); every mutation now runs in a fresh
  **isolated `git archive HEAD` copy** (the old code claimed this but mutated
  the live tree and restored); each mutation first proves a **baseline PASS**
  on the unmutated copy and then requires the kill to match a per-mutation
  `expect_fail_text` signature (wrong-reason kills are reported as FAIL);
  added **M6** (remove the new `orderBy` from `market_features`) and **M7**
  (reverse order direction on `read_analytics_table`). The harness aborts if
  the tracked tree is dirty so `git archive HEAD` is the code under test.
- **`api/trading_days.py` docstring:** the "inclusive of `end`" claim was
  inaccurate — the loop counts weekdays **strictly before** `end`
  (`start_for_trading_days(Wed, 5)` = prior Wednesday). Docstring rewritten to
  match the tested behavior (incl. the weekend roll-back note). No behavior change.

## Blocking findings
(none)

## Non-blocking notes
- `market_features_intraday` (db/delta_adapter.py:475) and `read_table` (:401)
  remain nondeterministic on **both** backends (no `ORDER BY` anywhere in their
  path). Not a backend-disagreement defect, but a follow-up should add
  `ORDER BY feature_ts DESC` (intraday) to both the warehouse builder and the
  Spark branch together, and decide on an explicit ordering contract for
  `read_table`.
- `read_analytics_cdc_state` `.limit(1)` is arbitrary if `analytics_cdc_state`
  ever holds more than one row; fine for a single-row state table.
- COT ordering column is `report_date` (the time column in `_COT_COLS`); the
  `.limit(1)` now deterministically returns the newest report on both backends.
- `tests/api/test_public_demo_security.py::test_peer_mode_single_bucket` is
  flaky under full-suite runs (shared time-window rate limiter leaks state
  across tests; passed alone and on the full-suite re-run). Pre-existing, not
  touched by this round.
- `tests/lakebase` fails in this environment on unmodified HEAD too
  (`db/lakebase.py:98 RuntimeError` building the Lakebase pool — needs a live
  Postgres). Outside the acceptance scope (`tests/api tests/gold tests/agent`),
  unchanged by this round (verified on a `git archive e5d2b56` copy).

## Checks run
- `git rev-parse HEAD` → `03990784f33cbfae074710cc9fd009908321f3c4` — pass
- `git status --porcelain --untracked-files=no` → clean — pass
- `python3 -m pytest tests/api tests/gold tests/agent -q` → `490 passed in 64.14s` — pass
  (485 baseline + 5 new tests; one earlier full-suite run showed
  `test_peer_mode_single_bucket` flaking — see notes; re-run green twice)
- `cd frontend && npx tsc --noEmit` → exit 0 — pass
- `cd frontend && npx vitest run` → `Test Files 16 passed (16) · Tests 246 passed (246)` — pass
- `cd frontend && npm run build` → `✓ built in 2.11s` — pass
- `python3 .agents/run-mutations.py` (isolated `git archive 0399078` copies, conftest loaded) → M1-M7 all PASS — pass

## Mutation transcript (`python3 .agents/run-mutations.py`)

```
mutation harness: isolated copies from `git archive 03990784f33cbfae074710cc9fd009908321f3c4`
pytest runs with the repo conftest loaded (no --noconftest)

============================================================
MUTATION M1: Remove orderBy in tools_retrieval (options read)
  target: tests/agent/test_tools_retrieval_ordering.py::test_orderBy_called_before_limit
  kill signature required: 'is not in list'
============================================================
  baseline: test PASSES on unmutated copy
  test FAILED (expected) via the expected kill signature
  pytest failure excerpt:
  E       ValueError: 'orderBy' is not in list

============================================================
MUTATION M2: Replace trading-day helper call with timedelta in market.py
  target: tests/api/test_trading_days.py::TestMarketRouteTradingDays::test_start_time_matches_helper_output
  kill signature required: 'helper output'
============================================================
  baseline: test PASSES on unmutated copy
  test FAILED (expected) via the expected kill signature
  pytest failure excerpt:
  E       AssertionError: start_time 2026-01-28T12:00:00Z != helper output 2025-10-20T12:00:00Z
  E       assert '2026-01-28T12:00:00Z' == '2025-10-20T12:00:00Z'

============================================================
MUTATION M3: Change null P&L back to zero-coercion
  target: tests/api/test_portfolio_null_pnl.py::test_null_pnl_serializes_as_json_null
  kill signature required: 'should be null'
============================================================
  baseline: test PASSES on unmutated copy
  test FAILED (expected) via the expected kill signature
  pytest failure excerpt:
  E       AssertionError: realized_pnl should be null, got 0.0
  E       assert 0.0 is None

============================================================
MUTATION M4: Remove count guard from SQL z-score
  target: tests/gold/test_zscore_window_guard.py::test_gold_sql_count_guard_produces_null_for_small_windows
  kill signature required: 'expected NULL'
============================================================
  baseline: test PASSES on unmutated copy
  test FAILED (expected) via the expected kill signature
  pytest failure excerpt:
  E           AssertionError: Row for 2026-01-02 has vol_count=2 but z-score is 0.7071067811865475, expected NULL
  E           assert 0.7071067811865475 is None

============================================================
MUTATION M5: Make start_for_trading_days ignore weekends
  target: tests/api/test_trading_days.py::TestStartForTradingDays::test_wednesday_back_5_trading_days
  kill signature required: '2026, 9, 30'
============================================================
  baseline: test PASSES on unmutated copy
  test FAILED (expected) via the expected kill signature
  pytest failure excerpt:
  E       assert datetime.date(2026, 10, 2) == datetime.date(2026, 9, 30)
  E        +  where datetime.date(2026, 9, 30) = date(2026, 9, 30)

============================================================
MUTATION M6: Remove the new orderBy from market_features_daily (r2)
  target: tests/agent/test_delta_adapter_ordering.py::test_market_features_orders_event_date_desc_before_limit
  kill signature required: 'never applied orderBy'
============================================================
  baseline: test PASSES on unmutated copy
  test FAILED (expected) via the expected kill signature
  pytest failure excerpt:
  E       AssertionError: db.delta_adapter.market_features: Spark branch never applied orderBy before limit
  E       assert 'orderBy' in ['where', 'select', 'limit']

============================================================
MUTATION M7: Reverse order direction on read_analytics_table (r2)
  target: tests/agent/test_delta_adapter_ordering.py::test_read_analytics_table_orders_event_date_desc_before_limit
  kill signature required: 'must be descending'
============================================================
  baseline: test PASSES on unmutated copy
  test FAILED (expected) via the expected kill signature
  pytest failure excerpt:
  E       AssertionError: db.delta_adapter.read_analytics_table: orderBy must be descending (newest first), got: Column<'event_date ASC NULLS FIRST'>

============================================================
MUTATION TEST SUMMARY
============================================================
  M1: PASS — tests/agent/test_tools_retrieval_ordering.py::test_orderBy_called_before_limit
  M2: PASS — tests/api/test_trading_days.py::TestMarketRouteTradingDays::test_start_time_matches_helper_output
  M3: PASS — tests/api/test_portfolio_null_pnl.py::test_null_pnl_serializes_as_json_null
  M4: PASS — tests/gold/test_zscore_window_guard.py::test_gold_sql_count_guard_produces_null_for_small_windows
  M5: PASS — tests/api/test_trading_days.py::TestStartForTradingDays::test_wednesday_back_5_trading_days
  M6: PASS — tests/agent/test_delta_adapter_ordering.py::test_market_features_orders_event_date_desc_before_limit
  M7: PASS — tests/agent/test_delta_adapter_ordering.py::test_read_analytics_table_orders_event_date_desc_before_limit

All 7 mutation tests passed (mutations detected by tests, for the expected reason, in isolated git-archive copies).
HARNESS_EXIT=0
```

M4 kills via the semantic NULL assertion (`z-score is 0.707…, expected NULL`),
not a parser error. M2/M3 kill via their real assertions (conftest loaded).
Each kill was verified against a baseline PASS of the same test on the
unmutated copy of the same `git archive` extraction.
