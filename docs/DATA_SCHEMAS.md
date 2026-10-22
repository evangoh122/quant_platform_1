
## Provenance: `data_source`

Under the owner rule of 2026-10-22, every **new** table, view, config row, snapshot record and knowledge-graph row
produced from that date onward carries a non-null `data_source` holding exactly one code from the controlled
vocabulary in `config/data_sources.py` (`DATA_SOURCES` + `validate_data_source`; unknown, empty or non-string
values raise). This is a forward rule, not a description of the current schema: existing tables — for example
`bronze_ohlcv`, whose provider column is `source` (see its listing below) — and existing config files
(`config/universe.yaml`, `config/tickers.yaml`) do not carry `data_source` yet, and no table listed in this file
has one today. The only rows that do are the ten research-symbol rows in `config/research_symbols.yaml`.

| code | meaning |
|---|---|
| `massive` | Massive (Polygon) S3 flat files / REST (OHLCV, options, splits, dividends) |
| `sec_edgar` | SEC EDGAR filings and the submissions API (data.sec.gov/submissions) |
| `sec_companyfacts` | SEC XBRL Company-Facts API |
| `hyperliquid` | Hyperliquid info API (HIP-3 perps, funding, candles) |
| `binance_um` | Binance USD-M futures (data.binance.vision archives / API) |
| `config` | hand-maintained repository config (e.g. universe YAML) |
| `derived` | computed in this project from other rows (record the inputs' sources in lineage/docs where a row mixes sources) |

From 2026-10-22 onward, new SQL tables and views get `data_source STRING NOT NULL`; new YAML config rows declare
`data_source:` and their loader rejects a missing or unknown value; new Python records get a required `data_source`
field. Among the existing files, only the research group in `config/research_symbols.yaml` follows this today: its
ten rows declare `data_source: massive` (their prices come from Massive) and `config/research_symbols.py` rejects a
missing or unknown value. `config/universe.yaml` and `config/tickers.yaml` predate the rule and have no
`data_source` yet.

### bronze_ohlcv  (14 cols)
  symbol                             string NOT NULL
  event_ts                           timestamp NOT NULL
  open                               double
  high                               double
  low                                double
  close                              double
  volume                             bigint
  vwap                               double
  trade_count                        int
  timespan                           string
  source                             string
  raw_payload                        string
  ingest_ts                          timestamp NOT NULL
  source_file                        string

### bronze_ohlcv_day  (15 cols)
  symbol                             string
  event_ts                           timestamp
  event_date                         date
  event_year                         int
  open                               double
  high                               double
  low                                double
  close                              double
  volume                             bigint
  vwap                               double
  trade_count                        bigint
  timespan                           string
  source                             string
  source_file                        string
  ingest_ts                          timestamp

### bronze_options_quotes  (23 cols)
  option_symbol                      string NOT NULL
  underlying                         string NOT NULL
  expiry                             date
  strike                             double
  right                              string            -- allowed: 'call'/'put' (quotes path), 'C'/'P' (Quick Start); consumers MUST normalise via CASE WHEN
  bid                                double
  ask                                double
  bid_size                           int
  ask_size                           int
  midpoint                           double
  participant_ts                     timestamp NOT NULL
  sequence_id                        bigint
  source                             string
  raw_payload                        string
  ingest_ts                          timestamp NOT NULL
  last_price                         double
  volume                             bigint
  open_interest                      bigint
  implied_volatility                 double
  delta                              double
  gamma                              double
  theta                              double
  vega                               double

### bronze_options_trades  (21 cols)
  option_symbol                      string NOT NULL
  underlying                         string NOT NULL
  expiry                             date
  strike                             double
  right                              string            -- allowed: 'call'/'put' (quotes path), 'C'/'P' (Quick Start); consumers MUST normalise via CASE WHEN
  price                              double
  size                               int
  exchange                           string
  conditions                         array<int>
  participant_ts                     timestamp NOT NULL
  sequence_id                        bigint
  source                             string
  raw_payload                        string
  ingest_ts                          timestamp NOT NULL
  open                               double
  high                               double
  low                                double
  close                              double
  volume                             bigint
  vwap                               double
  trade_count                        int

### bronze_options_day  (18 cols)
  contract_symbol                    string
  underlying                         string
  expiry                             date
  strike                             double
  right                              string            -- allowed: 'PUT'/'CALL' (day-agg path), 'put'/'call' (quotes path leakage), 'P'/'C' (Quick Start); consumers MUST normalise via CASE WHEN UPPER(right) IN ('PUT','P') THEN 'PUT' WHEN UPPER(right) IN ('CALL','C') THEN 'CALL' END
  event_ts                           timestamp
  event_date                         date
  event_year                         int
  open                               double
  high                               double
  low                                double
  close                              double
  volume                             bigint
  trade_count                        bigint
  timespan                           string
  source                             string
  source_file                        string
  ingest_ts                          timestamp

### bronze_sec_filings  (19 cols)
  cik                                string NOT NULL
  accession_number                   string NOT NULL
  form_type                          string NOT NULL
  filing_date                        date
  accepted_ts                        timestamp
  company_name                       string
  ticker                             string
  source_url                         string
  filing_section                     string
  chunk_id                           string
  chunk_text                         string
  chunk_index                        int
  raw_payload_ref                    string
  source                             string
  ingest_ts                          timestamp NOT NULL
  primary_doc                        string
  filing_url                         string
  chunk_char_count                   int
  raw_payload                        string

### bronze_sec_filings_v2  (17 cols)
  record_key                         string
  ticker                             string
  cik                                string
  company_name                       string
  form_type                          string
  filing_date                        string
  accepted_ts                        timestamp
  accession_number                   string
  primary_doc                        string
  filing_url                         string
  chunk_id                           int
  filing_section                     string
  chunk_text                         string
  chunk_char_count                   int
  source                             string
  ingest_ts                          timestamp
  raw_payload                        string

### bronze_cftc_fut  (93 cols)
  Market_and_Exchange_Names          string
  As_of_Date_In_Form_YYMMDD          string
  Report_Date_as_YYYY-MM-DD          string
  CFTC_Contract_Market_Code          string
  CFTC_Market_Code                   string
  CFTC_Region_Code                   string
  CFTC_Commodity_Code                string
  Open_Interest_All                  string
  Dealer_Positions_Long_All          string
  Dealer_Positions_Short_All         string
  Dealer_Positions_Spread_All        string
  Asset_Mgr_Positions_Long_All       string
  Asset_Mgr_Positions_Short_All      string
  Asset_Mgr_Positions_Spread_All     string
  Lev_Money_Positions_Long_All       string
  Lev_Money_Positions_Short_All      string
  Lev_Money_Positions_Spread_All     string
  Other_Rept_Positions_Long_All      string
  Other_Rept_Positions_Short_All     string
  Other_Rept_Positions_Spread_All    string
  Tot_Rept_Positions_Long_All        string
  Tot_Rept_Positions_Short_All       string
  NonRept_Positions_Long_All         string
  NonRept_Positions_Short_All        string
  Change_in_Open_Interest_All        string
  Change_in_Dealer_Long_All          string
  Change_in_Dealer_Short_All         string
  Change_in_Dealer_Spread_All        string
  Change_in_Asset_Mgr_Long_All       string
  Change_in_Asset_Mgr_Short_All      string
  Change_in_Asset_Mgr_Spread_All     string
  Change_in_Lev_Money_Long_All       string
  Change_in_Lev_Money_Short_All      string
  Change_in_Lev_Money_Spread_All     string
  Change_in_Other_Rept_Long_All      string
  Change_in_Other_Rept_Short_All     string
  Change_in_Other_Rept_Spread_All    string
  Change_in_Tot_Rept_Long_All        string
  Change_in_Tot_Rept_Short_All       string
  Change_in_NonRept_Long_All         string
  Change_in_NonRept_Short_All        string
  Pct_of_Open_Interest_All           string
  Pct_of_OI_Dealer_Long_All          string
  Pct_of_OI_Dealer_Short_All         string
  Pct_of_OI_Dealer_Spread_All        string
  Pct_of_OI_Asset_Mgr_Long_All       string
  Pct_of_OI_Asset_Mgr_Short_All      string
  Pct_of_OI_Asset_Mgr_Spread_All     string
  Pct_of_OI_Lev_Money_Long_All       string
  Pct_of_OI_Lev_Money_Short_All      string
  Pct_of_OI_Lev_Money_Spread_All     string
  Pct_of_OI_Other_Rept_Long_All      string
  Pct_of_OI_Other_Rept_Short_All     string
  Pct_of_OI_Other_Rept_Spread_All    string
  Pct_of_OI_Tot_Rept_Long_All        string
  Pct_of_OI_Tot_Rept_Short_All       string
  Pct_of_OI_NonRept_Long_All         string
  Pct_of_OI_NonRept_Short_All        string
  Traders_Tot_All                    string
  Traders_Dealer_Long_All            string
  Traders_Dealer_Short_All           string
  Traders_Dealer_Spread_All          string
  Traders_Asset_Mgr_Long_All         string
  Traders_Asset_Mgr_Short_All        string
  Traders_Asset_Mgr_Spread_All       string
  Traders_Lev_Money_Long_All         string
  Traders_Lev_Money_Short_All        string
  Traders_Lev_Money_Spread_All       string
  Traders_Other_Rept_Long_All        string
  Traders_Other_Rept_Short_All       string
  Traders_Other_Rept_Spread_All      string
  Traders_Tot_Rept_Long_All          string
  Traders_Tot_Rept_Short_All         string
  Conc_Gross_LE_4_TDR_Long_All       string
  Conc_Gross_LE_4_TDR_Short_All      string
  Conc_Gross_LE_8_TDR_Long_All       string
  Conc_Gross_LE_8_TDR_Short_All      string
  Conc_Net_LE_4_TDR_Long_All         string
  Conc_Net_LE_4_TDR_Short_All        string
  Conc_Net_LE_8_TDR_Long_All         string
  Conc_Net_LE_8_TDR_Short_All        string
  Contract_Units                     string
  CFTC_Contract_Market_Code_Quotes   string
  CFTC_Market_Code_Quotes            string
  CFTC_Commodity_Code_Quotes         string
  CFTC_SubGroup_Code                 string
  FutOnly_or_Combined                string
  report_date                        date
  report_year                        int
  release_ts                         timestamp
  source_dataset                     string
  source_file                        string
  ingest_ts                          timestamp

### bronze_cot  (21 cols)
  report_date                        date NOT NULL
  market_code                        string NOT NULL
  contract_name                      string
  open_interest                      bigint
  dealer_long                        bigint
  dealer_short                       bigint
  dealer_spread                      bigint
  asset_mgr_long                     bigint
  asset_mgr_short                    bigint
  asset_mgr_spread                   bigint
  lev_money_long                     bigint
  lev_money_short                    bigint
  lev_money_spread                   bigint
  other_rpt_long                     bigint
  other_rpt_short                    bigint
  non_rpt_long                       bigint
  non_rpt_short                      bigint
  release_ts                         timestamp
  source                             string
  raw_payload                        string
  ingest_ts                          timestamp NOT NULL

### silver_ohlcv  (15 cols)
  symbol                             string NOT NULL
  event_ts                           timestamp NOT NULL
  open                               double NOT NULL
  high                               double NOT NULL
  low                                double NOT NULL
  close                              double NOT NULL
  volume                             bigint
  vwap                               double
  trade_count                        int
  timespan                           string
  mid                                double
  is_regular_session                 boolean
  bar_missing                        boolean
  dedup_hash                         string
  processed_ts                       timestamp NOT NULL

### silver_options_quotes  (18 cols)
  option_symbol                      string NOT NULL
  underlying                         string NOT NULL
  expiry                             date NOT NULL
  strike                             double NOT NULL
  right                              string NOT NULL
  bid                                double
  ask                                double
  bid_size                           int
  ask_size                           int
  midpoint                           double
  spread                             double
  spread_pct                         double
  is_stale                           boolean
  is_locked                          boolean
  is_crossed                         boolean
  participant_ts                     timestamp NOT NULL
  dedup_hash                         string
  processed_ts                       timestamp NOT NULL

### silver_options_trades  (16 cols)
  option_symbol                      string NOT NULL
  underlying                         string NOT NULL
  expiry                             date NOT NULL
  strike                             double NOT NULL
  right                              string NOT NULL
  open                               double
  high                               double
  low                                double
  close                              double
  volume                             int
  trade_count                        int
  vwap                               double
  notional                           double
  participant_ts                     timestamp NOT NULL
  dedup_hash                         string
  processed_ts                       timestamp NOT NULL

### silver_sec_sections  (13 cols)
  cik                                string NOT NULL
  ticker                             string
  accession_number                   string NOT NULL
  form_type                          string NOT NULL
  filing_date                        date
  accepted_ts                        timestamp NOT NULL
  filing_section                     string NOT NULL
  chunk_id                           string NOT NULL
  chunk_index                        int
  chunk_text                         string
  chunk_char_count                   int
  source_url                         string
  processed_ts                       timestamp NOT NULL

### silver_sec_entities  (14 cols)
  cik                                string NOT NULL
  ticker                             string
  accession_number                   string NOT NULL
  form_type                          string NOT NULL
  accepted_ts                        timestamp NOT NULL
  entity_type                        string NOT NULL
  entity_key                         string
  entity_value                       string
  entity_unit                        string
  period_start                       date
  period_end                         date
  confidence                         double
  source_chunk_id                    string
  processed_ts                       timestamp NOT NULL

### silver_cot_positions  (15 cols)
  report_date                        date NOT NULL
  market_code                        string NOT NULL
  contract_name                      string
  mapped_asset                       string
  open_interest                      bigint
  dealer_net                         bigint
  asset_mgr_net                      bigint
  lev_money_net                      bigint
  other_rpt_net                      bigint
  non_rpt_net                        bigint
  dealer_pct_oi                      double
  asset_mgr_pct_oi                   double
  lev_money_pct_oi                   double
  release_ts                         timestamp NOT NULL
  processed_ts                       timestamp NOT NULL

### gold_ohlcv_features  (23 cols)
  symbol                             string NOT NULL
  feature_ts                         timestamp NOT NULL
  information_available_ts           timestamp NOT NULL
  return_1m                          double
  return_5m                          double
  return_15m                         double
  return_30m                         double
  log_return_1m                      double
  log_return_5m                      double
  log_return_15m                     double
  log_return_30m                     double
  rvol_5m                            double
  rvol_15m                           double
  rvol_30m                           double
  atr_14                             double
  momentum_5m                        double
  momentum_15m                       double
  rsi_14                             double
  vwap_deviation                     double
  relative_volume                    double
  dist_session_high                  double
  dist_session_low                   double
  processed_ts                       timestamp NOT NULL

  return_N = close / NULLIF(LAG(close, N) over (symbol, session day) ...) - 1 and
  log_return_N = LN(close / NULLIF(LAG(close, N) over the same window)) are
  companion minute features: the log return equals LN(1 + return_N) wherever it
  is defined, uses the same (symbol, DATE(event_ts)) partitioning so nothing
  leaks across sessions, and is NULL when the lagged bar is missing or the close
  ratio is non-positive (LN never sees 0 or a negative ratio). Both are computed
  from raw silver_ohlcv closes (unadjusted) and are available at
  information_available_ts = feature_ts + 1 minute like the rest of the row.

### gold_options_features  (16 cols)
  symbol                             string NOT NULL
  feature_ts                         timestamp NOT NULL
  information_available_ts           timestamp NOT NULL
  put_volume                         bigint
  call_volume                        bigint
  put_call_ratio                     double
  iv_atm                             double
  iv_25d_put                         double
  iv_25d_call                        double
  iv_skew                            double
  iv_term_slope                      double
  avg_spread_pct                     double
  volume_anomaly_zscore              double
  oi_concentration                   double
  net_delta_exposure                 double
  processed_ts                       timestamp NOT NULL

### gold_sec_features  (13 cols)
  ticker                             string NOT NULL
  accession_number                   string NOT NULL
  form_type                          string NOT NULL
  information_available_ts           timestamp NOT NULL
  sentiment_score                    double
  tone_positive                      double
  tone_negative                      double
  tone_uncertainty                   double
  risk_factor_change                 double
  filing_similarity                  double
  material_event_flag                boolean
  event_type                         string
  processed_ts                       timestamp NOT NULL

### gold_cot_features  (12 cols)
  mapped_asset                       string NOT NULL
  report_date                        date NOT NULL
  information_available_ts           timestamp NOT NULL
  lev_money_net                      bigint
  lev_money_net_chg_1w               bigint
  lev_money_pctile_52w               double
  lev_money_zscore_52w               double
  asset_mgr_net                      bigint
  asset_mgr_pctile_52w               double
  crowding_score                     double
  regime_label                       string
  processed_ts                       timestamp NOT NULL

### gold_model_features  (31 cols)
  symbol                             string NOT NULL
  prediction_ts                      timestamp NOT NULL
  feature_snapshot_id                string NOT NULL
  return_1m                          double
  return_5m                          double
  return_15m                         double
  return_30m                         double
  rvol_5m                            double
  rvol_15m                           double
  rvol_30m                           double
  atr_14                             double
  rsi_14                             double
  vwap_deviation                     double
  relative_volume                    double
  put_call_ratio                     double
  iv_atm                             double
  iv_skew                            double
  iv_term_slope                      double
  volume_anomaly_zscore              double
  sec_sentiment_score                double
  sec_risk_factor_change             double
  sec_material_event                 boolean
  cot_lev_money_zscore               double
  cot_crowding_score                 double
  cot_regime_label                   string
  model_version                      string
  processed_ts                       timestamp NOT NULL
  ohlcv_available_ts                 timestamp
  options_available_ts               timestamp
  sec_available_ts                   timestamp
  cot_available_ts                   timestamp

### gold_trading_signals  (10 cols)
  signal_id                          string NOT NULL
  symbol                             string NOT NULL
  prediction_ts                      timestamp NOT NULL
  horizon                            string NOT NULL
  direction                          string NOT NULL
  probability                        double NOT NULL
  model_version                      string NOT NULL
  feature_snapshot_id                string NOT NULL
  status                             string NOT NULL
  processed_ts                       timestamp NOT NULL

### sec_ingest_log  (16 cols)
  run_id                             string NOT NULL
  ticker                             string NOT NULL
  cik                                string NOT NULL
  accession_number                   string NOT NULL
  form_type                          string NOT NULL
  filing_date                        string
  accepted_ts                        timestamp
  status                             string NOT NULL
  rows_appended                      int
  attempt                            int
  error_code                         string
  error_message                      string
  started_ts                         timestamp
  completed_ts                       timestamp
  dry_run                            boolean
  logged_ts                          timestamp NOT NULL

### sec_cik_mapping_log  (7 cols)
  ticker                             string NOT NULL
  lookup_symbol                      string
  cik                                string
  status                             string NOT NULL   (mapped | missing | ambiguous)
  reason                             string
  mapped_ts                          timestamp
  run_id                             string

### gold_sec_coverage  (7 cols)
  ticker                             string NOT NULL
  cik                                string
  n_filings                          bigint NOT NULL
  n_chunks                           bigint NOT NULL
  first_filed                        timestamp
  last_filed                         timestamp
  last_ingest_ts                     timestamp

### gold_sec_kg_nodes  (7 cols)
  node_id                            string NOT NULL
  node_type                          string NOT NULL
  label                              string NOT NULL
  properties_json                    string NOT NULL
  concept_norm                       string
  provenance                         array<struct<accession_number:string,source_chunk_id:string,accepted_ts:timestamp>> NOT NULL
  build_version                      string NOT NULL

### gold_sec_kg_edges  (11 cols)
  edge_id                            string NOT NULL
  src_id                             string NOT NULL
  edge_type                          string NOT NULL
  dst_id                             string NOT NULL
  valid_from                         timestamp NOT NULL
  accession_number                   string NOT NULL
  source_chunk_id                    string NOT NULL
  accepted_ts                        timestamp NOT NULL
  confidence                         double
  properties_json                    string NOT NULL
  build_version                      string NOT NULL

### gold_sec_kg_build_runs  (9 cols)
  run_id                             string NOT NULL
  build_version                      string NOT NULL
  run_ts                             timestamp NOT NULL
  input_rows_by_entity_type          map<string,int> NOT NULL
  accepted_rows                      int NOT NULL
  rejected_rows                      int NOT NULL
  rejection_reasons                  map<string,int> NOT NULL
  node_count                         int NOT NULL
  edge_count                         int NOT NULL

### gold_tradable_universe  (6 cols)
  trade_date                         date NOT NULL
  symbol                             string NOT NULL
  med_adv_60d                        double
  adv_rank                           int
  information_available_ts           timestamp NOT NULL
  processed_ts                       timestamp NOT NULL

### gold_regime_features  (10 cols)
  trade_date                         date NOT NULL
  rsp_spy_ratio                      double
  rsp_spy_ratio_sma50                double
  rsp_spy_ratio_zscore_252           double
  rsp_spy_ratio_slope_20d            double
  breadth_regime                     string
  qqq_spy_20d                        double
  rsp_spy_20d                        double
  information_available_ts           timestamp NOT NULL
  processed_ts                       timestamp NOT NULL

### bronze_corporate_actions  (6 cols)
  symbol                             string NOT NULL
  ex_date                            date NOT NULL
  split_ratio                        double NOT NULL
  source                             string NOT NULL
  fetched_ts                         timestamp NOT NULL
  information_available_ts           timestamp NOT NULL

  Natural key: (symbol, ex_date, source)  — fetched_ts is NOT part of the key.
  Append-only: no update, delete, overwrite, or replaceWhere.
  split_ratio is new-shares / old-shares (20.0 for AMZN 20:1, 0.1 for 1:10 reverse).
  information_available_ts is ex-date 09:30 America/New_York converted to naive UTC.
  A same-key correction with different split_ratio is a conflict and is not silently applied.

  Source: Massive REST API only (source='massive').  Key via Databricks secret scope
          evangoh_capstone/massive_s3_secret_key or env var MASSIVE_API_KEY.

  Silver: only source='massive' rows are used for adjustment.  Deduplication to one
  row per (symbol, ex_date) — latest fetched_ts wins (Massive can return the same
  split twice across runs).  Other sources are ignored (not deleted).

  Important: adjusted prices are back-adjusted — historical levels change when a later
  split is loaded.  Returns are unaffected.  PIT consumers must use returns (return_1d),
  not historical adjusted levels (adj_close).

### silver_ohlcv_day_adjusted  (24 cols)
  symbol                             string NOT NULL
  event_date                         date NOT NULL
  event_ts                           timestamp
  open                               double
  high                               double
  low                                double
  close                              double
  volume                             bigint
  vwap                               double
  trade_count                        int
  cumulative_split_ratio             double
  price_adjustment_factor            double
  adj_open                           double
  adj_high                           double
  adj_low                            double
  adj_close                          double
  adj_vwap                           double
  adj_volume                         double
  raw_overnight_return               double
  adjusted_return_1d_unmasked        double
  return_1d                          double
  is_data_quality_break              boolean
  information_available_ts           timestamp
  processed_ts                       timestamp NOT NULL

  Natural key: (symbol, event_date).
  Idempotent: MERGE on key.  A new future split changes historical adj_* levels.
  adj_* columns are GLOBAL/CURRENT-SCALE back-adjusted display levels.
  They are approved for computing returns (ratios cancel within split-free
  intervals, and across ex-dates the prior bar includes the split while the
  ex-date bar does NOT).  They are NOT approved as model price-level features
  at a historical observation time — use PIT-adjusted prices instead.
  return_1d is the canonical return: NULL when is_data_quality_break = TRUE,
  otherwise adj_close / LAG(adj_close) - 1.  Never zero-filled for masked dates.
  information_available_ts is 16:30 America/New_York on the bar date (daily close).

  Coverage: gold_tradable_universe symbols, the SPY/RSP/QQQ benchmarks, and the
  research_universe symbols from config/research_symbols.yaml (ten commodity ETFs:
  GLD, IAU, SLV, SIVR, USO, BNO, UNG, CPER, PPLT, PALL).  Research symbols are
  research coverage only: they never enter gold_model_features or the published
  baseline signals, and config/universe.yaml (the trading universe) must stay
  disjoint from them.
  Adjustment scope: SPLIT-ONLY.  Distributions/dividends are NOT adjusted (the
  corporate-action scope is stock splits from bronze_corporate_actions), so an
  ETF ex-distribution gap remains in adj_* returns and return_1d.
  Return formulas, copied from silver/08_silver_ohlcv_day_adjusted.sql:
    adjusted_return_1d_unmasked
        = adj_close / NULLIF(LAG(adj_close) OVER (PARTITION BY symbol
                                                   ORDER BY event_date), 0) - 1
      where adj_close = close * (1.0 / NULLIF(COALESCE(cumulative_split_ratio,
                                                       1.0), 0)).
    return_1d = adjusted_return_1d_unmasked, but NULL while a masked
      data-quality break exists on the row.
    raw_overnight_return
        = raw_gross_return - 1.0
        = close / NULLIF(LAG(close) OVER (PARTITION BY symbol
                                          ORDER BY event_date), 0) - 1
      i.e. built from UNADJUSTED closes.
  The two return columns therefore use different price inputs.  Because
  raw_overnight_return is unadjusted, it jumps on splits: a 1-for-4 reverse
  split shows about +300% raw (the price multiplies by 4) against 0% adjusted.
  Do NOT use return_1d or raw_overnight_return as the opening-gap label:
  neither is the opening gap.  The gap label is
  next-session adj_open / previous-session adj_close - 1.

### data_quality_breaks  (14 cols)
  symbol                             string NOT NULL
  event_date                         date NOT NULL
  previous_event_date                date
  previous_close                     double
  close                              double
  raw_overnight_return               double
  matched_split_ratio                double
  post_split_gross_return            double
  split_error                        double
  classification                     string NOT NULL
  reason                             string
  is_masked                          boolean NOT NULL
  reviewed_by                        string
  reviewed_ts                        timestamp
  detected_ts                        timestamp NOT NULL
  processed_ts                       timestamp NOT NULL

  Natural key: (symbol, event_date).
  Classification values:
    SPLIT_EXPLAINED        — same-date split within 3% tolerance; not masked
    UNEXPLAINED_PENDING    — no matching split or residual > 3%; masked until reviewed
    CONFIRMED_DATA_BREAK   — human-verified data error (e.g. META ticker reuse); masked
    ALLOW_REAL_MOVE        — human-verified genuine move; not masked, return restored
  Manual review decisions (reviewed_by IS NOT NULL) are preserved on rerun.
  is_masked = TRUE for UNEXPLAINED_PENDING and CONFIRMED_DATA_BREAK.
  Masking sets return_1d = NULL (never 0) in silver_ohlcv_day_adjusted.

### bronze_sec_submissions  (7 cols)
  cik                                string NOT NULL
  payload                            string
  payload_sha256                     string NOT NULL
  http_status                        int NOT NULL
  fetched_at                         timestamp NOT NULL
  ingest_run_id                      string NOT NULL
  data_source                        string NOT NULL

  Source: https://data.sec.gov/submissions/CIK##########.json (SEC submissions
  API).  CIKs come from distinct non-null gold_sec_coverage.cik.
  data_source is always 'sec_edgar', from the controlled vocabulary in
  config/data_sources.py (UC column comment set by the writer DDL).
  Fair access: descriptive User-Agent from SEC_EDGAR_USER_AGENT (env or
  Databricks secret evangoh_capstone/sec_edgar_user_agent; never hard-coded),
  <= 8 requests/s, retries with backoff.  A 404 is a recorded miss:
  payload IS NULL and payload_sha256 = sha256('sec-submissions-missing') with
  http_status = 404.
  Natural key: (cik, payload_sha256).  Append-only: the writer only INSERTs
  when the key is absent, so reruns with an unchanged payload are no-ops.
  payload is the raw JSON text exactly as fetched; fetched_at is the
  observation time, stamped when the response completes (never before the
  request and never back-dated).

### silver_sec_registrant  (15 cols)
  cik10                              string
  payload_sha256                     string
  name                               string
  sic                                string
  sic_description                    string
  tickers                            array<string>
  exchanges                          array<string>
  state_of_incorporation             string
  fiscal_year_end                    string
  entity_type                        string
  observed_at                        timestamp
  ingest_run_id                      string
  data_source                        string NOT NULL
  processed_ts                       timestamp
  is_latest                          boolean

  One row per (cik10, payload_sha256) parsed from bronze_sec_submissions, so a
  CIK has many rows by design (one per distinct payload) — that is the identity
  history.  is_latest is TRUE on the row with the newest observed_at per cik10
  (payload_sha256 breaks ties): filter is_latest for the current attributes and
  use observed_at as-of for history.
  404 misses (payload IS NULL) are excluded.  name is the current legal name
  as of that payload; sic is kept as a string (leading zeros are significant);
  fiscal_year_end is the SEC MMDD value verbatim.  tickers/exchanges are
  observations at observed_at (ingest time) and are never back-dated.
  data_source is always 'sec_edgar' (config/data_sources.py).

### silver_sec_registrant_former_names  (9 cols)
  cik10                              string
  payload_sha256                     string
  former_name                        string
  from_date                          date
  to_date                            date
  observed_at                        timestamp
  ingest_run_id                      string
  data_source                        string NOT NULL
  processed_ts                       timestamp

  One row per (cik10, payload_sha256, former_name, from_date), exploded from
  payload.formerNames.  from_date is part of the key because a registrant can
  reuse a name across two periods (A -> B -> A); the same name published for
  two periods yields two rows.  The SEC publishes the bounds as ISO-8601
  midnight-UTC timestamps ("2001-04-02T00:00:00.000Z"); from_date/to_date keep
  the published calendar date (try_to_date(substring(..., 1, 10))) and stay
  inclusive as published (no +/- 1 day adjustment).  try_to_date, not to_date:
  a published value that is not a calendar date becomes NULL instead of
  aborting the refresh under ANSI mode (NULL means "not a date", never "no
  interval date").  data_source is always 'sec_edgar'
  (config/data_sources.py).
## data_source vocabulary (owner rule 2026-10-22)

**Scope: rows produced on or after 2026-10-22.**  Tables, views, config rows,
snapshots and KG rows that already existed before that date do **not** gain the
column and are not retrofitted; the requirement applies to every row this
project produces from that date onwards.  For those new rows, every table, view,
config row, snapshot record and KG node/edge/evidence row carries
`data_source STRING NOT NULL` (Python/JSON: a required `data_source` field)
holding exactly one code from `config/data_sources.py`:

    massive          Massive (Polygon) S3 flat files / REST
    sec_edgar        SEC EDGAR filings and the submissions API
    sec_companyfacts SEC XBRL Company-Facts API
    hyperliquid      Hyperliquid info API (HIP-3 perps, funding, candles)
    binance_um       Binance USD-M futures (data.binance.vision / API)
    config           hand-maintained repository config
    derived          computed in this project from other rows

`validate_data_source` rejects an empty, unknown or non-string code, and a row
that mixes providers is two rows. This PR adds contracts only: no table, view or
DDL is created yet.

### Perp tables (planned P2 — not deployed; 1h/15m forward capture is P1)

No perps table exists on this branch yet; the design is in docs/data/PERPS_WEEKEND_PLAN.md §4.
Every perps table, when it lands, carries:

  instrument_type                    string NOT NULL   -- always 'perpetual_future' (config/perp_universe.INSTRUMENT_TYPE)
  underlying_type                    string NOT NULL   -- equity | etf | fund | preferred | commodity | crypto
  underlying_symbol                  string NOT NULL   -- tracked ticker/commodity (e.g. NVDA, gold, BTC)
  venue                              string NOT NULL   -- hyperliquid | binance_usdm
  contract_symbol                    string NOT NULL   -- venue contract symbol (same value as symbol)
  data_source                        string NOT NULL   -- one provider code from config/data_sources.py

  Meaning: these rows are perpetual futures (derivatives), so instrument_type is
    'perpetual_future' on every row and is never inherited from the underlying;
    underlying_symbol records what the perp tracks (a listed equity/ETF/fund/
    preferred ticker, a commodity, or BTC/ETH) and contract_symbol is the venue
    contract, not the underlying's ticker.  A perp is never merged into the
    Security it tracks.  Required columns and rule: RULE-perps-are-derivatives
    (owner 2026-10-22); schema detail in docs/data/PERPS_WEEKEND_PLAN.md §4.

  Meaning (data_source): the upstream system that produced the row; one code per row, never null.
    hyperliquid  -> bronze_perp_candles, bronze_perp_funding, bronze_perp_oi_snapshots,
                    silver_perp_bars_1h, silver_perp_funding
    binance_um   -> bronze_binance_um_klines, bronze_binance_um_funding, bronze_binance_um_metrics
    derived      -> gold_weekend_perp_features (perp inputs hyperliquid; equity/options inputs massive;
                    record the input sources in lineage)
  Vocabulary (config/data_sources.py): massive, sec_edgar, sec_companyfacts, hyperliquid,
    binance_um, config, derived.  The Unity Catalog column comment names the code and that path.

  Scope applies to the Binance control tables too: bronze_binance_um_klines/funding/metrics
    carry venue=binance_usdm, instrument_type=perpetual_future, underlying_type=crypto,
    underlying_symbol=BTC/ETH and contract_symbol=symbol, so no control row can be read as spot.

  Weekend label (gold_weekend_perp_features, docs/data/PERPS_WEEKEND_PLAN.md §4.3):
    open_gap = session_open / prev_session_close - 1 on RAW official prints, with the explicit
    split/dividend factor effective at that open (bronze_corporate_actions) stored as
    label_split_factor; prev_session_close is Thursday's close on a Friday-holiday weekend.
    Prediction cutoffs are rows: sun_1800, sun_2000, mon_0400, mon_0900.

  Unity Catalog metadata (every perps table):
    TABLE COMMENT starts "Perpetual futures (derivatives), not equities:"
    table tags: instrument_type=perpetual_future, asset_class=derivative
    price column comments: "perp mark/trade price, not the stock price"
