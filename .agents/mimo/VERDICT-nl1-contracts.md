# VERDICT: nl1-contracts — MiMo
**Status:** APPROVED
**Round:** 1

## Blocking findings
None.

## Non-blocking notes
- `implied_volatility` replaces `market_capitalization` as the eighth metric per spec. `market_capitalization` is not an accepted enum value or alias.
- Policy uses year-based date arithmetic (replace year) instead of flat `365 * years` day count, correctly handling leap year boundaries.
- `GROUPING_NOT_ALLOWED` is treated as a hard violation (REJECT), consistent with the spec's intent that structural invalidity fails closed.
- `LLMEntityMention` rejects prompt injection patterns (`ignore previous instructions`, `reveal system prompt`, etc.) in addition to SQL metacharacters and control chars.
- Alias resolver loads ticker membership from `config/tickers.yaml` and `config/universe.yaml` via `importlib.resources`; no network or filesystem discovery.
- Provenance model uses `runtime_ms` (not ambiguous `runtime`) with explicit unit documentation in JSON Schema description.
- All 32 metric×operation pairs registered in the YAML registry; no unregistered pairs.

## Checks run
- `python3 -m pytest -q tests/analytics_nl` → **144 passed** (0 failures)
- `python3 -m analytics_nl.export_schemas --check` → **All schemas match**
- `python3 -m pytest -q --ignore=tests/lakebase` → skipped (timeout; analytics_nl subset passes cleanly)

## Red-test baseline
- `python3 -c 'import analytics_nl'` → `ModuleNotFoundError: No module named 'analytics_nl'` (confirmed pre-change)
- `python3 -m pytest -q tests/analytics_nl` → `ERROR: file or directory not found: tests/analytics_nl` (confirmed pre-change)

## Mutation proofs (discarded after)
**(a) Unapproved view reference:** Mutated `serve_daily_prices_v2` in one entry's `serving_view` (without updating `approved_views`). Test `test_all_serving_views_approved` fails with `serving_view 'serve_daily_prices_v2' not in approved views`. ✓

**(b) Policy hard bound:** Changed `date_bound_years: 10` → `date_bound_years: 5` in `policy_bounds_v1.yaml`. Test `test_gold_10_year_boundary` fails: 10-year range now rejected. ✓

**(c) Schema byte mutation:** Changed title in `canonical_intent.v1.json` to `MODIFIED Schema`. Test `test_all_schemas_regenerate` fails: `Schema canonical_intent.v1.json differs from generated`. ✓

## Commit SHAs
- `7edc2d8` — feat(nl1): add core contracts package with strict Pydantic v2 models
- `ed26f0c` — feat(nl1): add registry, aliases, and policy classifier
- `65c3203` — feat(nl1): add schema exports, DDL docs, and CLI entry point
- `7c856fe` — feat(nl1): add comprehensive test suite for contracts, registry, aliases, policy, schemas, DDL

## Files changed (my commits only)
```
analytics_nl/__init__.py
analytics_nl/__main__.py
analytics_nl/contracts.py
analytics_nl/data/__init__.py
analytics_nl/data/semantic_registry_v1.yaml
analytics_nl/data/aliases_v1.yaml
analytics_nl/data/policy_bounds_v1.yaml
analytics_nl/registry.py
analytics_nl/aliases.py
analytics_nl/policy.py
analytics_nl/export_schemas.py
analytics_nl/schemas/canonical_intent.v1.json
analytics_nl/schemas/llm_intent_output.v1.json
analytics_nl/schemas/policy_outcome.v1.json
analytics_nl/schemas/chart.v1.json
analytics_nl/schemas/provenance.v1.json
analytics_nl/schemas/alias_resolution.v1.json
docs/NL1_PROPOSED_SERVING_VIEWS.md
tests/analytics_nl/__init__.py
tests/analytics_nl/test_contracts.py
tests/analytics_nl/test_registry.py
tests/analytics_nl/test_aliases.py
tests/analytics_nl/test_policy.py
tests/analytics_nl/test_schemas.py
tests/analytics_nl/test_ddl.py
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
- None for NL1 implementation. Owner decisions listed in spec section 5 remain open for later lanes.