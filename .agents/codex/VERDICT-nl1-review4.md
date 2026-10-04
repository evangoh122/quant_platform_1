===VERDICT START===
Status: CHANGES_REQUESTED

Findings:

1. High — Sparse-IV coverage fails open when statistics contain no observations. `analytics_nl/policy.py:267-271` only evaluates coverage when `total_count > 0`; `(0, 0)` adds no rejection reason. Direct probes for IV trend, compare, rank, and aggregate all returned `CHEAP / ACCEPTED_CHEAP`. Zero-total or otherwise invalid statistics must produce `INSUFFICIENT_DATA`, with validation for `0 <= sample_count <= total_count`.

2. High — Bronze fallback views understate output availability. `docs/NL1_PROPOSED_SERVING_VIEWS.md:114-115` and `:617-618` publish only the derived 16:30 market-close timestamp, despite selecting rows by the later `ingest_ts`. A row dated January 2 but ingested January 5 was experimentally emitted with January 2 availability in both fallback views. Output availability must be `GREATEST(derived_timestamp, ingest_ts)` so downstream PIT consumers cannot treat late data as historically available.

3. Medium — Registry validation is not fail-closed. `analytics_nl/registry.py:180-223` accepts unsupported metric/operation keys, arbitrary identifier-shaped aggregation tokens and required slots; `:225-255` does not close output scalar types; `:301-308` checks only for missing expected pairs and permits extras. Direct mutations also showed acceptance of unused approved views, unknown parameter types, and defaults outside parameter bounds. This contradicts the required fixed-token, exact-coverage registry contract.

4. Medium — Policy bounds loading silently repairs malformed policy data. `analytics_nl/policy.py:88-110` substitutes security bounds and thresholds with `.get(..., default)` and performs no type, positivity, ordering, policy-version, or exact-bound validation beyond the semantic-model version check at `:81-82`. Missing or malformed checked-in limits must raise `PolicyValidationError`, not become valid defaults.

5. Medium — The adjusted-return availability regression remains unprotected. Removing `adj.information_available_ts` from the production-document `GREATEST` at `docs/NL1_PROPOSED_SERVING_VIEWS.md:172` left all 386 tests passing. The generic availability test at `tests/analytics_nl/test_ddl.py:944-955` counts window-derived timestamps but does not require every availability-bearing joined input to contribute. A late adjusted-return revision could therefore regress without detection.

Required checks:

- `python3 -m pytest tests/analytics_nl -q` — 386 passed.
- `python3 -m analytics_nl.export_schemas --check` — All schemas match.
- Trailing-newline ticker, index, and sector IDs — all rejected via full-match validation.
- IV 12/19,390 and absent-stat probes — `INSUFFICIENT_DATA` for all four operations.
- Relative performance currently has the start-date bounds, excludes masked NULL returns, propagates −100% returns to NULL/`invalid_return`, and combines entity plus benchmark availability.
- Semantic SQL tests obtain their SQL from `docs/NL1_PROPOSED_SERVING_VIEWS.md` through `tests/analytics_nl/_ddl_extract.py`.

Independent document mutations:

- Drop adjusted-source availability from the equity join — SURVIVED: 386 passed.
- Remove both bronze `ingest_ts <= :as_of` predicates — killed: 1 failed, 385 passed.
- Move adjusted daily-price `:as_of` filtering after `ROW_NUMBER` — killed: 1 failed, 385 passed.

Repository working tree remained unchanged.
===VERDICT END===
