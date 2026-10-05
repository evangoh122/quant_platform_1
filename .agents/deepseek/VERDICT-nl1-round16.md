===VERDICT START===
# VERDICT: nl1-round16 — DeepSeek (checker)
**Status:** CHANGES_REQUESTED
**Round:** 16

Range verified: `f5eb265..HEAD` (9 commits: `03f222b`, `df6ea45`, `a75ebb4`, `2c07797`, `d27cbb5`, `f0204a9`, `223c28f`, `12e18ef` verdict, `e1a62f1` check request). Source read-only; every mutation performed in `/tmp/r16m*` copies created via `git archive HEAD | tar -x` and never committed. Working tree untouched by this check.

MiMo's "6 mutation tests, all pass from archived copy" is not a mutation proof. Those in-test `test_mutation_*` methods mutate a **hard-coded SQL string inside the test file** and assert a self-fulfilling fact about that string; they never read the production DDL. I re-ran each mutation against the **production** `docs/NL1_PROPOSED_SERVING_VIEWS.md` / `analytics_nl/contracts.py` / `analytics_nl/policy.py`. Three of the seven items survive — the reviewer's findings are not actually closed.

## Blocking findings

1. **[High — item 2 not closed] `tests/analytics_nl/test_ddl.py:1079` (`TestRelativePerformanceDuckDB._RELPERF_SQL`) is a hard-coded copy of the relative-performance SQL, not extracted from `docs/NL1_PROPOSED_SERVING_VIEWS.md`.**
   - Mutation (a): `THEN NULL` → `THEN -0.99` at doc lines 429 & 457 → **361 passed** (SURVIVES). The named test `test_minus_100_percent_day_gives_null_and_invalid_return` still passes because it runs `_RELPERF_SQL`, not the doc. The only doc-level test, `test_anomaly_propagation_for_invalid_returns` (test_ddl.py:684), checks substrings only (`BOOL_OR`, `return_1d <= -1`, `invalid_return`, `CASE`) — all still present.
   - Mutation (b): `WHEN e.has_invalid_return OR b.has_invalid_bench THEN 'invalid_return'` → `WHEN FALSE THEN 'invalid_return'` at doc line 478 → **361 passed** (SURVIVES).
   - Failure scenario: an engineer edits the production view to drop the NULL arm (or the invalid_return status) and the suite stays green; a −100% day then produces a numeric `cumulative_return` / `status='ok'` instead of NULL/`invalid_return`. Build request item 2 explicitly required "extract the relative-performance SQL" — that extraction was not implemented.

2. **[Medium — item 3 not closed] momentum availability + LAG ordering are not enforced against the production DDL.**
   - Mutation (a): remove `momentum_20d_info_ts` from the final `GREATEST(...)` (both adjusted & fallback blocks, doc :258-263 and :365-370) → **361 passed** (SURVIVES). `test_output_availability_is_window_max` (test_ddl.py:912) checks only the tokens *present* in the GREATEST; it never requires every CTE-defined availability source (`momentum_20d_info_ts` is still defined via `MAX(...) OVER` in `with_momentum`) to appear in the final GREATEST.
   - Mutation (b): `WHERE return_1d IS NOT NULL` added to `with_momentum` (adjusted mode) so `LAG(close,20)` runs on the filtered series → **361 passed** (SURVIVES). No test checks LAG-before-null-filter ordering.
   - Failure scenario: a late revision of the t−20 bar no longer advances `information_available_ts` (PIT look-ahead), and in adjusted mode `LAG(close,20)` counts non-trading rows again — both silent.

3. **[Medium — item 5 not closed] bounded-bars dedup-before-LAG is not enforced against the production DDL.**
   - Mutation: remove `WHERE rn = 1` from the `with_splits` CTE (so the `suspected_split` LAG runs over non-deduped rows) at doc :656-657 → **361 passed** (SURVIVES). `TestBoundedBarsDuckDB` (test_ddl.py:1275) runs two hard-coded strings `_DEDUP_THEN_LAG_SQL` / `_LAG_BEFORE_DEDUP_SQL` and asserts the "correct" one detects a split; it never reads the production bounded-bars DDL.
   - Failure scenario: the production view regresses to LAG-before-dedup, duplicate `(symbol, event_date)` rows corrupt the LAG ratio (≈1), and splits are silently missed — the suite stays green.

## Mutation proof table (run against PRODUCTION DDL/code, not test helpers)

| # | Item | Mutation | Named test expected to fail | Result |
|---|------|----------|------------------------------|--------|
| 1a | 1 | `GREATEST(e.entity_info_ts, b.bench_max_info_ts)` → `GREATEST(e.entity_info_ts)` | `test_relative_performance_includes_benchmark_availability` + `test_output_availability_is_window_max` | **2 failed** — caught |
| 1b | 1 | whole GREATEST → `e.entity_info_ts AS information_available_ts` | same two | **2 failed** — caught |
| 2a | 2 | production `THEN NULL` → `THEN -0.99` (doc :429,:457) | `test_minus_100_percent_day_gives_null_and_invalid_return` | **0 failed (361 passed)** — SURVIVED |
| 2b | 2 | production status CASE → `WHEN FALSE THEN 'invalid_return'` (doc :478) | `test_minus_100_percent_day_gives_null_and_invalid_return` | **0 failed (361 passed)** — SURVIVED |
| 3a | 3 | drop `momentum_20d_info_ts` from final GREATEST (both blocks) | `test_output_availability_is_window_max` | **0 failed (361 passed)** — SURVIVED |
| 3b | 3 | `WHERE return_1d IS NOT NULL` on `with_momentum` (LAG on filtered series) | (none named) | **0 failed (361 passed)** — SURVIVED |
| 4 | 4 | remove `AND ingest_ts <= :as_of` (both bronze fallbacks) | `test_bronze_fallback_has_ingest_ts_bound` | **1 failed** — caught |
| 5 | 5 | remove `WHERE rn = 1` from `with_splits` (LAG before dedup) | (none named) | **0 failed (361 passed)** — SURVIVED |
| 6 | 6 | `_TICKER_RE.fullmatch` → `_TICKER_RE.match` (contracts.py:223) | `test_trailing_newline_rejected` | **1 failed** ("DID NOT RAISE") — caught |
| 7 | 7 | coverage check reverted to fail-open on missing `coverage_stats` (policy.py:257-271) | `test_no_coverage_stats_fails_closed` | **1 failed** — caught |

## Non-blocking notes

- Items 1, 4, 6, 7 are correctly protected: each has a production-level test that fails on the mutation, and my independent production-mutation runs confirm it.
- Item 7 secondary requirement "threshold configurable/documented" is only partly met: `min_coverage_ratio` was tightened 0.001 → 0.5 and is configurable in `analytics_nl/data/semantic_registry_v1.yaml` (`coverage: {availability: snapshot_only, min_coverage_ratio: 0.5}`), but the 0.5 semantics are not explained anywhere outside the YAML. Not blocking.
- The self-referential mutation tests (`test_mutation_replace_null_arm_with_computed_value_fails` :1221, `test_mutation_disable_invalid_return_status_fails` :1249, `TestBoundedBarsDuckDB` :1275) assert facts about their own hard-coded strings and pass regardless of what the production DDL says. They provide false confidence and should either extract from the production DDL or be removed.

## Checks run

- `python3 -m pytest tests/analytics_nl -q` (repo @HEAD) → **361 passed** (16.9s).
- `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest tests/analytics_nl -q` → **361 passed** (pyspark hidden, no pyspark import).
- `python3 -m analytics_nl.export_schemas --check` → "All schemas match."
- Mutation dirs `/tmp/r16m{1a,1b,2a,2b,3a,3b,4,5,6,7}`: each `git archive HEAD | tar -x` copy, single mutation applied, `python3 -m pytest tests/analytics_nl -q` run → results in table above.
===VERDICT END===
