
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
  right                              string
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
  right                              string
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
  right                              string
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

### gold_ohlcv_features  (19 cols)
  symbol                             string NOT NULL
  feature_ts                         timestamp NOT NULL
  information_available_ts           timestamp NOT NULL
  return_1m                          double
  return_5m                          double
  return_15m                         double
  return_30m                         double
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