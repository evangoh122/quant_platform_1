# Analytics ontology

These YAML files are the machine-readable vocabulary for NL analytics and point-in-time feature use. `table_semantics.yaml` is the table registry; references in filters, joins, metrics, and the SEC knowledge graph must resolve to that registry.

All analytical joins are point-in-time: select only rows whose `information_available_ts` is at or before the query or prediction timestamp. At source and silver layers, use the documented native availability timestamp (`accepted_ts`, `release_ts`, `participant_ts`, or a bar-close timestamp) to derive that canonical field. Never substitute business dates such as `filing_date`, `report_date`, or `observation_date` for availability.

Daily equity prices in `bronze_ohlcv_day` are unadjusted. Cross-day return, realized-volatility, drawdown, momentum, and relative-performance analytics must use `silver_ohlcv_day_adjusted` (directly or through a governed serving view). Existing intraday features that still use raw prices are marked `price_adjustment: unadjusted` and must exclude corporate-action boundaries.

The five `serve_*_v1` tables are proposals, not live relations. They remain `status: proposed` until an owner or Databricks administrator executes and verifies the DDL in `docs/NL1_PROPOSED_SERVING_VIEWS.md`; any metric sourced from one is likewise marked proposed.

Corporate-action split ratios use the normalized convention `new shares / old shares`: forward splits are greater than one and reverse splits are between zero and one. Massive is the sole implemented corporate-actions source (per `etl/corporate_actions.py` MassiveCorporateActionsSource and the refresh notebook).

Perpetual futures are **derivatives, not equities**: every perps row carries `instrument_type = perpetual_future` with `underlying_type`, `underlying_symbol`, `venue` and `contract_symbol`, and a perp is never merged into the security it tracks. Perps history is read from flat-file archives (`hyperliquid` requester-pays S3 fills, asset contexts and funding events; `binance_um` Vision zips) and rebuilt into bars by trade time in UTC, with `information_available_ts = bar_end_ts`. Bars are never forward-filled, a fill is counted once per id/hash, and a bar built from fills is a perp trade (last) price — never the mark, oracle, stock or pre-market price. Vocabulary: `flat_file_archive`, `append_only_fill_bar`, `requester_pays`, `perpetual_future`, `perp_underlying`, `open_interest` in `business_terms.yaml`; schema detail in `docs/data/PERPS_WEEKEND_PLAN.md`.
