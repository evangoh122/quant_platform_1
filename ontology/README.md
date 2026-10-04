# Analytics ontology

These YAML files are the machine-readable vocabulary for NL analytics and point-in-time feature use. `table_semantics.yaml` is the table registry; references in filters, joins, metrics, and the SEC knowledge graph must resolve to that registry.

All analytical joins are point-in-time: select only rows whose `information_available_ts` is at or before the query or prediction timestamp. At source and silver layers, use the documented native availability timestamp (`accepted_ts`, `release_ts`, `participant_ts`, or a bar-close timestamp) to derive that canonical field. Never substitute business dates such as `filing_date`, `report_date`, or `observation_date` for availability.

Daily equity prices in `bronze_ohlcv_day` are unadjusted. Cross-day return, realized-volatility, drawdown, momentum, and relative-performance analytics must use `silver_ohlcv_day_adjusted` (directly or through a governed serving view). Existing intraday features that still use raw prices are marked `price_adjustment: unadjusted` and must exclude corporate-action boundaries.

The five `serve_*_v1` tables are proposals, not live relations. They remain `status: proposed` until an owner or Databricks administrator executes and verifies the DDL in `docs/NL1_PROPOSED_SERVING_VIEWS.md`; any metric sourced from one is likewise marked proposed.

Corporate-action split ratios use the normalized convention `new shares / old shares`: forward splits are greater than one and reverse splits are between zero and one. The current corporate-actions branch implements yfinance only. Massive is recorded as planned, with no source-precedence claim until its adapter exists.
