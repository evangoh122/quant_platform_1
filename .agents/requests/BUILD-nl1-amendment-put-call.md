# AMENDMENT to NL1 (owner decision, 2026-10-04)

The owner confirmed BOTH options metrics. The v1 metric set is now **9**:
price, return, volume, realized_volatility, drawdown, momentum, relative_performance,
**implied_volatility** (`gold_options_features.iv_atm`) AND **put_call_ratio**
(`gold_options_features.put_call_ratio`). Market cap stays out (no governed source).

Required changes in NL1:
- Add `put_call_ratio` to the metric enum, the registry, the alias registry ("put/call", "put call
  ratio", "PCR", "p/c ratio"), the metric definitions and the JSON schemas.
- Registry entry:
  - source: an approved serving view over `gold_options_features` (e.g. `serve_options_daily_v1`,
    DDL in the docs appendix), with `symbol`, `feature_ts` and `information_available_ts`;
  - operations: trend, compare, rank, aggregate;
  - aggregation: the mean of the daily ratio. Do NOT sum ratios;
  - units: ratio (dimensionless);
  - chart families: line and bar;
  - bounds: same as the other Gold metrics.
- Tests:
  - a valid intent for each operation on `put_call_ratio`;
  - "sum of put call ratio" is rejected or coerced with a disclosed assumption (pick one and test
    it);
  - the schema sync test includes the new enum value.
- Update the owner-decisions section: the 8th/9th metric decision is RESOLVED.
