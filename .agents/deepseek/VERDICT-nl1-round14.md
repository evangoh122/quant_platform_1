===VERDICT START===
# VERDICT: nl1-round14 — DeepSeek (checker)
**Status:** CHANGES_REQUESTED
**Round:** 14

Range verified: `8bb7f61..HEAD` (implementation commits 515cb0e "feat: extend sparse-data coverage checks…", a453089 "fix(tests): check registry output fields…", 27d0221 "feat: output availability = MAX…", 0d13099 "feat: relative performance over REQUESTED window", 82fc250 "feat: anomaly propagation for ≤−100% returns"). Source read-only; all mutations performed in `/tmp/nl1r14-mut-{a,b,c,d,e}` copies and discarded. Working tree clean at `41c3e2c`.

## Blocking findings

1. [tests/analytics_nl/test_ddl.py:618-652] `TestDDLAvailabilityContract::test_output_availability_is_window_max` is **vacuous against mutation (b)**. It only asserts the final `SELECT`'s `GREATEST(...)` references ≥2 availability tokens (`re.findall(r"(?:INFORMATION_AVAILABLE_TS|_INFO_TS|_AVAILABILITY)", args) >= 2`, lines 633-646). It never verifies that those tokens — `realized_vol_20d_info_ts`, `drawdown_info_ts` (docs/NL1_PROPOSED_SERVING_VIEWS.md:197,:223), `entity_info_ts` (:393), `bench_max_info_ts` (:419) — are actually defined as `MAX(information_available_ts) OVER (...)` in their CTEs.
   - Concrete failure scenario: replacing the rolling-window `MAX(information_available_ts) OVER (PARTITION BY symbol ORDER BY event_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)` for `realized_vol_20d_info_ts` with the bare current row `information_available_ts` leaves the final `GREATEST` with 3 tokens, so the assertion still passes. A late-arriving revision inside the 20-row window then yields an output `information_available_ts` earlier than a contributing row — precisely the PIT hazard item 1 must prevent — and no test fails.
   - Proof: `/tmp/nl1r14-mut-b` → `python3 -m pytest tests/analytics_nl -q` → **343 passed** (full suite green). BUILD-nl1-round14.md item 1 explicitly lists this mutation as one that must FAIL.

## Mutation proofs (re-run)

| # | Mutation | Expected | Actual | Result |
|---|----------|----------|--------|--------|
| a | remove benchmark availability from final GREATEST (docs:429 `GREATEST(e.entity_info_ts, b.bench_max_info_ts)` → `GREATEST(e.entity_info_ts)`) | FAIL | `TestDDLAvailabilityContract::test_output_availability_is_window_max` **1 failed** ("GREATEST must combine at least 2 availability timestamps, found 1") | caught |
| b | replace rolling-window `MAX(information_available_ts) OVER (...)` with current-row `information_available_ts` | FAIL | full suite **343 passed** | **NOT caught** |
| c | drop `:start_date` bound (both entity & benchmark input CTEs) | FAIL | `TestDDLRelativePerformanceSemantics::test_start_date_bound_in_inputs` **1 failed** ("must filter by event_date >= :start_date") | caught |
| d | rename `close_price`→`close_price_bogus` in bounded-bars DDL only (both variants) | FAIL | `test_registry_output_fields_match_view_columns` **1 failed** ("output_field 'close_price' not found in view 'serve_bounded_daily_bars_v1'") | caught |
| e | restrict coverage enforcement to `Operation.aggregate` only | FAIL | `test_iv_trend/compare/rank_coverage_check` **3 failed**, 66 passed | caught |

## Item 5 verification

- DDL uses a **window bool** (`BOOL_OR(return_1d <= -1) OVER (...)`) as the invalid-row detector and a `CASE` **outside** the `SUM` that nulls the cumulative series — not `CASE` inside `SUM` (which would skip the NULL term). Matches the requirement. Status field emits `'invalid_return'` via `CASE WHEN e.has_invalid_return OR b.has_invalid_bench`.
- No fixture test was added. `test_anomaly_propagation_for_invalid_returns` (test_ddl.py:540) is string-match only. I attempted the DuckDB semantic run for the −100% day: `SUM(LN(1 + return_1d))` raises `OutOfRangeException: cannot take logarithm of zero` because the window computes `LN(0)` for the −100% row regardless of the `CASE` short-circuit. Correct in Spark only because `LN(0) = -Infinity` and `CASE` discards the branch — so a DuckDB semantic test for item 5 is not even runnable against this DDL (see non-blocking notes).
- Item 3 semantics verified correct in DuckDB (no −100% rows): AAPL cumulative over [2024-01-02, 2024-01-03] = `(1.10*1.20)-1 = 0.32` (2024-01-01 `-0.50` excluded by `:start_date`); benchmark SPY = 0.21; `rel_perf` = 0.11. Window anchoring is achieved by the input-CTE filter, which is correct.

## Non-blocking notes

- [tests/analytics_nl/test_ddl.py:525] `test_start_date_bound_in_inputs` and [test_ddl.py:540] `test_anomaly_propagation_for_invalid_returns` are string-match, not semantic. BUILD-nl1-round14.md items 3 and 5 explicitly required a "contract/DuckDB test (extract the view SQL, run on a fixture)" (item 3) and "Test with a fixture containing a −100% day" (item 5). Mutation (c) is caught only because the literal string `event_date >= :start_date` disappears; a placement swap (filter moved after the window) would keep the string and go undetected by this test.
- [docs/NL1_PROPOSED_SERVING_VIEWS.md:367-398] The `SUM(LN(1 + return_1d))` window evaluates `LN(0)`/`LN(negative)` on invalid rows in engines that do not return `±Infinity` from `LN` (DuckDB raises). Safe on Spark/Databricks, but the DDL is not portable to the DuckDB harness the BUILD request implied.

## test_policy.py:982 correction

- Confirmed a correction, not a weakening: the only removed lines in the diff are the old `test_iv_trend_no_coverage_check` (docstring "non-aggregate does not trigger coverage check" + `assert ... not in result.reason_codes`), replaced by `test_iv_trend_coverage_check` asserting `INSUFFICIENT_DATA in result.reason_codes`. `git diff 8bb7f61..HEAD -- tests` shows **no test deleted or weakened**; all other changes are additive (new `test_iv_compare_coverage_check` :1000, `test_iv_rank_coverage_check` :1018, and the two new test_ddl classes).

## Schemas in sync

- `python3 -m analytics_nl.export_schemas --check` → "All schemas match."

## Checks run

- `python3 -m pytest tests/analytics_nl -q` → **343 passed** (14.6s).
- `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest tests/analytics_nl -q` → **343 passed** (pyspark hidden; no pyspark import).
- `python3 -m analytics_nl.export_schemas --check` → "All schemas match."
- `git status` → clean (working tree unchanged by this check).
===VERDICT END===
