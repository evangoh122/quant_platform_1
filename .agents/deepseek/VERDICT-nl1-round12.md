===VERDICT START===
# VERDICT: nl1-round12 — DeepSeek (checker)
**Status:** CHANGES_REQUESTED
**Round:** 12

Range verified: `614c5bf..HEAD` (commits f9ec128 "round12: fix Codex findings 1-5", eaece5d, 27d9bb8). Source read-only; all mutations performed in `/tmp/nl1r12-mut-*` copies and discarded.

## Blocking findings

1. [tests/analytics_nl/test_ddl.py:340] The PIT mutation proof does NOT hold. `_has_as_of_filter_before_window` extracts each CTE body as `body = sql_normalized[start:]` when no later `) , <cte> AS (` is found. For the *last* CTE this swallows everything to end-of-string, including the final `SELECT … WHERE rn = 1 AND information_available_ts <= :as_of`. So an as-of filter placed **after** a window (in the final `WHERE`) is still attributed to a CTE, and `len(as_of_ctes) > 0` returns True.
   - Mutation run (serve_options_metrics_v1): removed `WHERE information_available_ts <= :as_of` from `as_of_filtered` and added `AND information_available_ts <= :as_of` to the final `WHERE rn = 1` (i.e. moved the filter after the `ROW_NUMBER` window).
   - Result: `pytest tests/analytics_nl/test_ddl.py::TestDDLPITSafetyAsOfBeforeWindow::test_all_views_have_as_of_before_window -q` → **1 passed** (returncode 0). Expected FAIL per build item 1. The checker cannot distinguish "as-of before window" from "as-of after window".
   - The DDL itself is correct (all 8 view blocks apply the filter in an input CTE before any window/aggregate, and `serve_relative_performance_v1` emits `GREATEST(e.information_available_ts, b.bench_info_ts)`), but the contract test does not actually verify that property.

2. [tests/analytics_nl/test_source_schema.py:216] The SQL-column checker is still effectively empty, so the close/close_price mutation proof does NOT hold. `_extract_view_select_columns` keys on `re.match(r"^\s*SELECT\s", stripped)`; the DDL writes `SELECT` on its own line, so after `.strip()` the token is `SELECT` with no trailing whitespace and the regex never matches. `in_final_select` is never set, the function returns `set()` for every view, and `test_registry_output_fields_match_view_columns` skips every entry at [tests/analytics_nl/test_source_schema.py:256] (`if not view_cols: continue`). The test is vacuous.
   - Mutation run: renamed `close_price` → `close_price_bogus` in `price.trend` output_fields (semantic_registry_v1.yaml).
   - Result: `pytest tests/analytics_nl/test_source_schema.py::TestRegistryColumnsMatchViewOutput::test_registry_output_fields_match_view_columns -q` → **1 passed** (returncode 0). Expected FAIL per build item 2.
   - Verified `_extract_view_select_columns` returns `[]` for `serve_bounded_daily_bars_v1` and `serve_daily_prices_v1` in the unmodified tree.

## Non-blocking notes

- `CoverageStatus` (analytics_nl/contracts.py:117) is imported at analytics_nl/policy.py:16 but never referenced; the aggregate `status` output_field is a plain `string` with no enum binding or schema constraint tying it to `{ok, INSUFFICIENT_DATA}`. The enum exists but is not enforced anywhere.
- Relative-performance cumulative return `EXP(SUM(LN(1 + return_1d)))` (docs/NL1_PROPOSED_SERVING_VIEWS.md:336, :349) has no `return_1d > -1` guard; `r <= -1` yields `LN(0) = -inf` / `LN(negative) = NaN`. Safe in practice because daily returns on positive-priced equities are bounded above `-1`, and NULL data-quality breaks are excluded, but the assumption is not defensively guarded or documented in the DDL.
- `implied_volatility.aggregate` marks `agg_value` nullable unconditionally (not only when status is INSUFFICIENT_DATA) — acceptable loosening, but weaker than the "nullable only when INSUFFICIENT_DATA" wording.

## Verified working (mutation proofs)

- Item 3 coverage: `pytest …::TestInsufficientData::test_iv_aggregate_insufficient_data` with `if False: …` bypass → **1 failed** (returncode 1, `NORMAL != REJECT`). Proof holds.
- Item 4 entity kind: `pytest …::TestEntityKindValidation::test_sector_rejected_for_implied_volatility` with type-check no-op → **1 failed** (returncode 1, `CHEAP != REJECT`). Proof holds.
- Item 4 min/max + kinds: one-entity `price.compare` → `TOO_FEW_ENTITIES`; sector-level IV trend → `ENTITY_NOT_ALLOWED` (covered by the 329-test suite).
- Item 3 semantics: IV aggregate 2025 with `(12, 19390)` → `INSUFFICIENT_DATA`; put_call_ratio aggregate 2025 → allowed.
- Item 5: benchmark parameterised (`WHERE symbol = :benchmark`, no hardcoded `SPY`), cumulative return per side, `rel_perf = entity_cumulative − benchmark_cumulative`.

## Checks run

- `python3 -m pytest tests/analytics_nl -q` → 329 passed (11.5s).
- `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest tests/analytics_nl -q` → 329 passed (pyspark hidden; no pyspark import).
- `python3 -m analytics_nl.export_schemas --check` → "All schemas match."
- Item 6 `git diff 614c5bf..HEAD -- tests` → additions only; the 2 `-` lines are EOF-newline re-adds (`assert view in ddl_content`, `assert bounds.adjusted_source_available is False`), no tests deleted/weakened.
- Item 6 schemas regenerated: `policy_outcome.v1.json` gained `TOO_FEW_ENTITIES`, `INSUFFICIENT_DATA`; `export_schemas --check` confirms contracts match.
===VERDICT END===
