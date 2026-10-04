===VERDICT START===
# VERDICT: nl1-round17 — DeepSeek (checker)
**Status:** CHANGES_REQUESTED
**Round:** 17

Range verified: `7275130` (MiMo round-17 build). Source read-only; every mutation performed in `/tmp/r17m*` copies created via `git archive HEAD | tar -x -C /tmp/<dir>`. Working tree untouched by this check (the only unstaged change, `.agents/dispatch.sh` mode flip, is not mine).

Items 1 and 2 of the check request pass. Item 3 (Claude's COALESCE concern) is a **confirmed semantic change to production DDL made to get the DuckDB tests green**, and it is a blocking finding. One of the two round-16 momentum mutations (adjusted-mode LAG ordering) is still not closed.

## Blocking findings

1. **[High — item 3 confirmed] `docs/NL1_PROPOSED_SERVING_VIEWS.md:432` (`COALESCE(return_1d, 0)`) and `:459` (`COALESCE(bench_return, 0)`), together with the removal of `WHERE return_1d IS NOT NULL` (was `:441`) / `WHERE bench_return IS NOT NULL` (was `:466`), silently treat a masked/NULL return as 0%.**
   - A masked/NULL `return_1d` is a data-quality break. The documented contract (`docs/NL1_PROPOSED_SERVING_VIEWS.md:13-14` and `:709`) states: "nulls are never interpolated", "NULL values indicate data-quality breaks and are excluded from aggregates and disclosed". The new `COALESCE(return_1d, 0)` interpolates NULL → 0%, the exact thing the contract forbids.
   - Concrete failure scenario (verified against the extracted view SQL in DuckDB): fixture `return_1d = NULL` on 2024-01-02 → output row `rel_perf = 0.0299…`, `status = 'ok'`. The data-quality break is silently reported as a 0% day with a clean status; downstream consumers get a fabricated number with no disclosure. Previously (round 16) that day was excluded from the output.
   - The comment MiMo added (`:424-425`) claims NULL returns "propagate through BOOL_OR for anomaly detection". That is false: `BOOL_OR(return_1d <= -1)` evaluates to NULL for a NULL input and BOOL_OR ignores NULL, so a masked day does **not** set `has_invalid_return` (verified: `has_invalid = False` on the NULL day).
   - MiMo's justification (`VERDICT-nl1-round17.md:9`, "the NULL filters prevented BOOL_OR from detecting -100% returns") is factually wrong: a −100% day has `return_1d = -1.0`, which is NOT NULL and passes `WHERE return_1d IS NOT NULL`; BOOL_OR detects it fine. The real driver was DuckDB's eager `LN(0)` error, which is a DuckDB-only behaviour and could be fixed in the `to_duckdb()` shim alone (verified: round-16 DDL + a shim-only `LN(GREATEST(1 + col, 1e-10))` guard produces `cumulative = NULL`, `status = 'invalid_return'` correctly).
   - Correct behaviour must be specified and documented: either keep `WHERE … IS NOT NULL` (exclude masked days, matching the contract), or NULL the window, or introduce an explicit coverage flag — not silent 0% interpolation.

2. **[Medium — item 3b still open] adjusted-mode LAG-before-null-filter ordering is still not enforced against the production DDL.**
   - Mutation 4a: add `WHERE return_1d IS NOT NULL` to the **adjusted** `with_momentum` CTE (`FROM returns_from_source`, `docs/NL1_PROPOSED_SERVING_VIEWS.md:198`) → **383 passed (SURVIVES)**. The new `test_mutation_add_null_filter_to_momentum_breaks_lag` (`test_ddl.py:1408`) only inspects the **fallback** variant (`extract_view_sql(..., variant="fallback")`).
   - Failure scenario: an engineer adds a NULL-return filter before the adjusted momentum `LAG(close, 20)`; momentum then counts filtered rows and spans >20 calendar days across data-quality gaps — silent, suite stays green. This is the round-16 finding (3b, "adjusted mode") that was supposed to be closed.

## Non-blocking notes

- Items 1 and 2 (the five round-16 mutations) are now closed: each mutation against the production DOC fails (table below). The hard-coded `_RELPERF_SQL` / `_DEDUP_THEN_LAG_SQL` / `_LAG_BEFORE_DEDUP_SQL` are gone; `_PROD_SQL` is derived via `extract_view_sql()` + `to_duckdb()`; the in-test `CREATE TABLE base_*` fixtures are not stand-in view SQL. Helper has its own 16-test suite (`test_extract_helper.py`).
- `test_late_revision_changes_availability` (`test_ddl.py:1311`) is a structural string check (`assert "ROWS BETWEEN 20 PRECEDING AND CURRENT ROW" in sql`), not the semantic test the build request asked for ("output availability changes when a late revision of the t−20 bar has a later information_available_ts"). The mutation is still caught, but only structurally.
- `test_momentum_lag_spans_20_trading_rows_with_null_return_day` (`test_ddl.py:1275`) runs the **fallback** variant whose returns are computed from prices, so its fixture has no actual NULL-return day; the docstring claim ("with a NULL-return day") is misleading, and the adjusted-mode NULL-return momentum case is never exercised.
- MiMo note 12 ("fallback all returns non-NULL, behavioural testing impractical") is contradicted by the facts: the fallback first row's return IS NULL (from `LAG`), and my mutation-4 run did trip `test_momentum_lag_spans_20_trading_rows_with_null_return_day` in fallback mode.

## Mutation proof table (run against PRODUCTION DDL/doc in `git archive` copies)

| Mutation | Expected catch | Result |
|---|---|---|
| 1. `THEN NULL` → `THEN -0.99` | `test_minus_100_percent_day_gives_null_and_invalid_return` | **1 failed** — caught (cumulative = -1.0101) |
| 2. `WHEN e.has_invalid_return OR b.has_invalid_bench THEN 'invalid_return'` → `WHEN FALSE` | same | **1 failed** — caught (status = 'ok') |
| 3. remove `momentum_20d_info_ts` from final GREATEST | availability tests | **2 failed** — caught |
| 4. add `WHERE return_1d IS NOT NULL` to `with_momentum` (both variants) | momentum tests | **2 failed** — caught |
| 4a. add `WHERE return_1d IS NOT NULL` to adjusted `with_momentum` only | (none named) | **0 failed (383 passed)** — SURVIVED |
| 5. remove `WHERE rn = 1` from `with_splits` | `TestBoundedBarsDuckDB` | **3 failed** — caught |
| 6. momentum window frame 20 → 21 | `test_output_availability_is_window_max` + `test_late_revision_changes_availability` | **2 failed** — caught |

## Checks run

- `python3 -m pytest tests/analytics_nl -q` (repo @HEAD) → **383 passed** (14.8s).
- `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest tests/analytics_nl -q` → **383 passed** (pyspark hidden).
- `python3 -m analytics_nl.export_schemas --check` → "All schemas match."
- Mutation dirs `/tmp/r17m{1,2,3,4,4a,5,6}`: each `git archive HEAD | tar -x -C /tmp/<dir>` copy, single DOC mutation, `python3 -m pytest tests/analytics_nl -q` → results in table above.
- Empirical NULL-propagation check: `COALESCE(return_1d,0)` on a NULL day → `has_invalid=False`, cumulative unchanged; masked row emitted with `status='ok'`.
===VERDICT END===
