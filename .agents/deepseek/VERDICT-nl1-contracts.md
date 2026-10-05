===VERDICT START===
# VERDICT: nl1-contracts — DeepSeek (independent checker)
**Status:** CHANGES_REQUESTED
**Round:** 1 (HEAD 54f50cb, branch `slice/nl-contracts`)

## Blocking findings

1. **[docs/NL1_PROPOSED_SERVING_VIEWS.md:100-101 and :110-111] `SELECT *` in the proposed DDL.**
   `serve_daily_equity_metrics_v1` uses a bare `SELECT *` (split across two lines
   `SELECT` / `*,`) in the `with_vol` CTE (lines 100-101) and again in the
   `with_drawdown` CTE (lines 110-111). BUILD-nl1-contracts.md §1.6 ("No `SELECT *`")
   and CHECK-nl1-contracts.md item 6 ("has no `SELECT *`") both ban this, and the
   plan requires explicit columns for reproducibility. Concrete failure: the
   appendix does not enumerate every column each stage carries, so a source-column
   rename silently changes the view's output shape without a reviewer being able to
   see it from the DDL alone.

2. **[tests/analytics_nl/test_ddl.py:45-59] The `SELECT *` test cannot detect the
   violation above.** The assertion on line 57 is `assert "SELECT *" not in
   line.upper() or "SELECT * FROM" not in line.upper()` — an OR of two negations
   that is false only when a single line contains both `SELECT *` *and*
   `SELECT * FROM`. The DDL's `SELECT` and `*` are on separate lines, so the loop
   never matches and the test passes vacuously even though `SELECT *` is present.
   This is precisely the class of "test claims coverage it does not provide" that
   the protocol treats as a defect.

3. **[tests/analytics_nl/test_policy.py:274-287] Silver bounds are never tested at
   the classification level, and the only "silver" test actually exercises a Gold
   entry.** `test_silver_two_year_boundary` constructs `metric=price, operation=trend`
   (registry `price.trend` is `layer: gold`) and asserts
   `result.cost_class in (EXPENSIVE, NORMAL, CHEAP)`, which is a tautological pass.
   There is no test for the Silver edges: 2 years exactly vs 2 years + 1 day,
   10 tickers vs 11, 10,000 rows vs 10,001, nor "missing Silver scope". BUILD §1.10
   explicitly requires "Silver 2-year/10-ticker/10,000 boundaries, one-unit-over
   failures, missing Silver scope"; CHECK item 3 requires "Test the edge values
   (exactly at, just over)". Concrete failure: a regression that breaks the Silver
   date/ticker/row arithmetic would not be caught.

4. **[analytics_nl/data/semantic_registry_v1.yaml] No registry entry uses
   `layer: silver` (all 36 are `gold`), so the Silver branch of
   `classify_intent` (analytics_nl/policy.py:154-179) is unreachable in production
   and untested. The plan's policy table defines Silver as a real tier ("bounded
   Silver drill-down tables"), and BUILD §1.8 requires "Silver still requires
   entity+dates and never exceeds 2 years/10 tickers/10,000 rows". As shipped, that
   tier can never be reached by any valid intent. Either a Silver pair must be
   registered, or the Silver bound must be explicitly documented/tested via a
   synthetic entry so the classification path is proven.

## Non-blocking notes

- [analytics_nl/registry.py:134-239] The validator does not fail closed on several
  points the request lists: parameter `default` is never checked against `min`/`max`
  or `enum`; `allowed_grouping` / `required_slots` / `aggregation` are only
  regex-checked (`^[a-z_][a-z0-9_]*$`), not validated against the closed
  `Grouping` enum, the `{entities, date_range}` slot set, or a closed aggregation
  token set; `max_entities` is not bounded; and an extra pair key outside the
  metric×operation enum (e.g. `market_cap.trend`) is loaded without rejection (the
  coverage loop only asserts all enum pairs are *present*, never that non-enum keys
  are *absent*). Shipped data is correct, so this is robustness-only.
- [analytics_nl/registry.py:227 and :110-111; analytics_nl/policy.py:76-99] Hard
  bounds are duplicated as Python literals — `10000` in the registry validator,
  `max_entities=100`/`row_limit=10000` parse defaults, and `date_bound_years=10` /
  `row_bound=5000` / `ticker_bound=10` fallback defaults in `load_policy_bounds`.
  BUILD §1.8 says "Do not duplicate hard bounds as Python literals."
- [tests/analytics_nl/test_policy.py:193-205, :265-271; tests/analytics_nl/test_aliases.py:78-82;
  tests/analytics_nl/test_schemas.py:86-90] Several tests use conditional/try-asserts
  or `if`-guarded assertions (`test_too_many_tickers`, `test_invalid_grouping`,
  `test_case_sensitive_ticker`, `test_chart_discriminator`), so they can pass without
  asserting the thing their name promises. Not load-bearing today, but weak.
- [analytics_nl/aliases.py:188-215] `load_ticker_symbols` catches
  `FileNotFoundError`/`TypeError` but not `ModuleNotFoundError`, which is what
  `importlib.resources.files("config")` raises when `config` is not packaged with an
  installed `analytics_nl` wheel. The "when present" fallback therefore crashes
  rather than degrading, contrary to the installed-wheel requirement.
- [analytics_nl/schemas/provenance.v1.json:255-259] `runtime_ms` is named with the
  unit (good), but the field carries no `description` documenting milliseconds; the
  request asked the unit be documented in the schema description.
- [analytics_nl/registry.py:230] Stale comment "check all 8 metrics" — should be 9
  (the loop itself correctly iterates the 9-value `Metric` enum).
- [analytics_nl/aliases.py:229] `tz = ZoneInfo("America/New_York")` in
  `resolve_relative_date` is computed but unused (date arithmetic is tz-naive).

## Checks run

- `python3 -m pytest -q tests/analytics_nl` → **167 passed** (0 failures)
- `python3 -m analytics_nl.export_schemas --check` → **All schemas match** (exit 0)
- `python3 -m pytest -q --ignore=tests/lakebase` → **705 passed, 67 skipped** (0 failures)
- Independent probe: `load_ticker_symbols()` → GOOG/GOOGL/AAPL present, 12351 symbols.
- Independent probe: registry has 36 entries, no `market_cap*` key, `put_call_ratio.aggregate`
  has `aggregation == "mean_only"` and `agg_function.enum == ["mean"]` (sum rejected).
- Independent probe: `[k for k,e in registry.entries.items() if e.layer == "silver"]` → `[]`.

## Verified-correct (in scope)

- Metric enum is exactly the 9 required values; `market_capitalization` absent; the
  eighth/ninth metrics are `implied_volatility`/`put_call_ratio` per the owner amendment.
- Every Pydantic model is strict v2 (`extra="forbid", strict=True`); version
  constraints, `entity_type`/`chart_type` discriminators, and no-coercion behavior
  are real, not documentation-only (test_contracts.py).
- `LLMIntentOutput` JSON Schema contains none of the 12 forbidden property names
  (recursive test in test_contracts.py:527-550 and test_schemas.py:50-70); `sanitized_sql`
  appears only in `ProvenanceEnvelope`, isolated from LLM output.
- Registry identifiers match `^[a-z_][a-z0-9_]*$`; every `serve_*_v1` view is on the
  approved list; no Bronze/Silver/Gold physical table names leak into registry data.
- DDL cross-check: `serve_options_metrics_v1` exposes `iv_atm` + `put_call_ratio`,
  PIT-safe via `information_available_ts`, daily grain, dedup via `ROW_NUMBER()`,
  and the unexecuted/admin-only banner is present.
- Aliases are deterministic (explicit data + config membership, no comment parsing,
  no fuzzy/confidence); hostile text is rejected; relative dates use an injected
  America/New_York clock with DST/leap-year coverage.
- Schemas regenerate deterministically (`--check` passes), use `additionalProperties:
  false`, expose the `chart_type` discriminator, and contain no absolute paths/timestamps.
===VERDICT END===
