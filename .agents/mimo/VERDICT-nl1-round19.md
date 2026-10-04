# VERDICT: nl1-round19 — MiMo
**Status:** APPROVED
**Round:** 19

## Blocking findings
None — all 5 items implemented and verified.

## Non-blocking notes
- Item 1 (High): Coverage check now fails closed on (0,0), negative, and invalid stats. 6 new tests.
- Item 2 (High): Bronze fallback DDL updated to GREATEST(derived_ts, ingest_ts). 5 new DuckDB tests with mutation proofs.
- Item 3 (Medium): Registry rejects unknown metric/operation/aggregation/slot/type keys, defaults outside bounds, extra entries, unused views. 10 new tests.
- Item 4 (Medium): Policy bounds loading validates types, positivity, ordering, version. 11 new tests via monkeypatched YAML.
- Item 5 (Medium): Availability contract test now detects GREATEST-based CTE sources. Mutation test proves adj.information_available_ts removal fails.
- Total test count: 386 (baseline) → 419 (+33 new tests, 0 removed, 0 weakened).

## Checks run
- `python3 -m pytest tests/analytics_nl -q` → 419 passed
- `python3 -m analytics_nl.export_schemas --check` → All schemas match
- `python3 -c "import pyspark"` → ModuleNotFoundError (pyspark not on PYTHONPATH)