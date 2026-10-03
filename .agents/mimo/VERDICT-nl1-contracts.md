# VERDICT: nl1-contracts — MiMo
**Status:** APPROVED
**Round:** 2

## Blocking findings
None.

## Non-blocking notes
- `put_call_ratio` added as 9th metric per owner amendment (2026-10-04). `implied_volatility` remains 8th. `market_capitalization` stays excluded.
- Metric aliases: "put/call", "put call ratio", "PCR", "p/c ratio" all resolve to `put_call_ratio` via new `metric_aliases` section in `aliases_v1.yaml` and `resolve_metric()` method on `AliasResolver`.
- `put_call_ratio.aggregate` uses `mean_only` aggregation token (custom, not reused from other metrics) with `agg_function` enum restricted to `[mean]` only. Summing a ratio is mathematically invalid — the registry enforces this at the contract level rather than adding policy-layer agg-function validation.
- `put_call_ratio` output fields are `nullable: true` (consistent with `implied_volatility`) because options data coverage is sparse — not all underlyings have options data on all dates.
- Serving view `serve_options_metrics_v1` DDL updated to expose `put_call_ratio` alongside `iv_atm`.
- Owner decision for 8th/9th metric marked RESOLVED in `BUILD-nl1-contracts.md` section 5.
- All 36 metric×operation pairs registered in the YAML registry; no unregistered pairs.

## Checks run
- `python3 -m pytest -q tests/analytics_nl` → **167 passed** (0 failures)
- `python3 -m analytics_nl.export_schemas --check` → **All schemas match**
- `python3 -m pytest -q --ignore=tests/lakebase` → **705 passed, 67 skipped** (0 failures)

## Red-test baseline
New tests would fail on HEAD (`465db0d`) because:
- `test_exact_metric_count` expects 9 (HEAD has 8)
- `test_put_call_ratio_present` (new)
- `test_entry_count` expects 36 (HEAD has 32)
- `TestPutCallRatioEntries` — 6 tests requiring `put_call_ratio.*` registry entries (HEAD has 0)
- `TestMetricAliases` — 7 tests requiring `resolve_metric()` and metric_aliases data (HEAD has neither)
- `TestPutCallRatioPolicy` — 5 tests requiring valid put_call_ratio intents (HEAD rejects as unregistered pair)
- `test_put_call_ratio_*_intent` — 4 contract-level intent tests (HEAD rejects metric value)

## Mutation proofs (discarded after)
**(a) Unapproved view reference:** Mutated `serve_daily_prices_v2` in one entry's `serving_view` (without updating `approved_views`). Test `test_all_serving_views_approved` fails. ✓

**(b) Policy hard bound:** Changed `date_bound_years: 10` → `date_bound_years: 5` in `policy_bounds_v1.yaml`. Test `test_gold_10_year_boundary` fails. ✓

**(c) Schema byte mutation:** Changed title in `canonical_intent.v1.json` to `MODIFIED Schema`. Test `test_all_schemas_regenerate` fails. ✓

**(d) put_call_ratio sum rejection:** Verified `put_call_ratio.aggregate` has `agg_function.enum: [mean]` — `sum` is not in the enum. Test `test_aggregate_enum_allows_only_mean` proves this. ✓

## Files changed (round 2 delta)
```
analytics_nl/contracts.py                      (+1: put_call_ratio enum member)
analytics_nl/aliases.py                        (+21: metric_aliases loading + resolve_metric method)
analytics_nl/data/aliases_v1.yaml              (+7: metric_aliases section)
analytics_nl/data/semantic_registry_v1.yaml    (+87: 4 put_call_ratio registry entries)
analytics_nl/schemas/canonical_intent.v1.json  (regenerated: 9th enum value)
analytics_nl/schemas/llm_intent_output.v1.json (regenerated: 9th enum value)
analytics_nl/schemas/provenance.v1.json        (regenerated: intent nested schema)
docs/NL1_PROPOSED_SERVING_VIEWS.md             (+4: put_call_ratio in DDL)
tests/analytics_nl/test_contracts.py           (+59: put_call_ratio intent tests, metric count)
tests/analytics_nl/test_registry.py            (+39: TestPutCallRatioEntries, entry count)
tests/analytics_nl/test_aliases.py             (+34: TestMetricAliases)
tests/analytics_nl/test_policy.py              (+72: TestPutCallRatioPolicy)
.agents/requests/BUILD-nl1-contracts.md        (+3: owner decision RESOLVED)
```

## Scope exclusions
- No API routes, HTTP/SSE code, or Databricks client changes
- No SQL compilation, LLM calls, or frontend code
- No changes to `api/`, `evals/`, `strategies/`, `agent/`, `pipelines/`
- No changes to `.agents/dispatch.sh`
- No secrets or absolute paths in committed files

## Offline/Windows notes
- All code uses `importlib.resources` for data file loading; works from Windows and installed wheel
- No network calls in tests; clock injection for relative dates
- LF line endings on all text files
- Python 3.12.3, Pydantic 2.13.5, PyYAML 6.0.1, pytest 9.1.1

## Unresolved assumptions
- None for NL1 round 2. Owner 8th/9th metric decision RESOLVED (2026-10-04).