-- silver_cot_positions: bronze_cftc_fut -> silver_cot_positions
--
-- COT data landed in bronze_cftc_fut / bronze_cftc_com (bronze_cot is 0 rows).
-- This transform reads the futures-only table (bronze_cftc_fut, FutOnly) as the
-- authoritative source; bronze_cftc_com is the futures+options combined view and
-- is near-identical (15,437 vs 15,427 rows). Choice documented in the verdict.
--
-- Normalizes TFF participant categories into *_net and *_pct_oi columns:
--   dealer_net   = Dealer long - short
--   asset_mgr_net = Asset_Mgr long - short
--   lev_money_net = Lev_Money long - short
--   other_rpt_net = Other_Rept long - short
--   non_rpt_net  = NonRept long - short
-- `market_code` is the trimmed CFTC contract market code; `mapped_asset` maps
-- the contract name to an asset-class regime. `release_ts` is the official
-- CFTC release timestamp (PIT key).
--
-- Idempotent: MERGE on (report_date, market_code).

MERGE INTO bootcamp_students.evangoh_capstone.silver_cot_positions AS tgt
USING (
  SELECT
    report_date,
    TRIM(`CFTC_Contract_Market_Code`)   AS market_code,
    `Market_and_Exchange_Names`          AS contract_name,
    CASE
      WHEN UPPER(`Market_and_Exchange_Names`) LIKE '%S&P%'
        OR UPPER(`Market_and_Exchange_Names`) LIKE '%E-MINI%'
        OR UPPER(`Market_and_Exchange_Names`) LIKE '%NASDAQ%'
        OR UPPER(`Market_and_Exchange_Names`) LIKE '%DOW JONES%'
        OR UPPER(`Market_and_Exchange_Names`) LIKE '%DJIA%'
        OR UPPER(`Market_and_Exchange_Names`) LIKE '%RUSSELL%'
        OR UPPER(`Market_and_Exchange_Names`) LIKE '%MSCI%'
        OR UPPER(`Market_and_Exchange_Names`) LIKE '%NIKKEI%'
        OR UPPER(`Market_and_Exchange_Names`) LIKE '%VIX%'      THEN 'equity_index'
      WHEN UPPER(`Market_and_Exchange_Names`) LIKE '%UST%'
        OR UPPER(`Market_and_Exchange_Names`) LIKE '%SOFR%'
        OR UPPER(`Market_and_Exchange_Names`) LIKE '%FED FUNDS%'
        OR UPPER(`Market_and_Exchange_Names`) LIKE '%ERIS%'
        OR UPPER(`Market_and_Exchange_Names`) LIKE '%EURO SHORT TERM RATE%' THEN 'rate'
      WHEN UPPER(`Market_and_Exchange_Names`) LIKE '%BITCOIN%'
        OR UPPER(`Market_and_Exchange_Names`) LIKE '%ETHER%'     THEN 'crypto'
      WHEN UPPER(`Market_and_Exchange_Names`) LIKE '%DOLLAR%'
        OR UPPER(`Market_and_Exchange_Names`) LIKE '%POUND%'
        OR UPPER(`Market_and_Exchange_Names`) LIKE '%YEN%'
        OR UPPER(`Market_and_Exchange_Names`) LIKE '%FRANC%'
        OR UPPER(`Market_and_Exchange_Names`) LIKE '%PESO%'
        OR UPPER(`Market_and_Exchange_Names`) LIKE '%REAL%'
        OR UPPER(`Market_and_Exchange_Names`) LIKE '%RAND%'
        OR UPPER(`Market_and_Exchange_Names`) LIKE '%XRATE%'
        OR UPPER(`Market_and_Exchange_Names`) LIKE '%USD INDEX%' THEN 'fx'
      WHEN UPPER(`Market_and_Exchange_Names`) LIKE '%COMMODITY%' THEN 'commodity'
      ELSE 'other'
    END                                   AS mapped_asset,
    TRY_CAST(TRIM(`Open_Interest_All`) AS BIGINT)        AS open_interest,
    TRY_CAST(TRIM(`Dealer_Positions_Long_All`) AS BIGINT)
      - TRY_CAST(TRIM(`Dealer_Positions_Short_All`) AS BIGINT)   AS dealer_net,
    TRY_CAST(TRIM(`Asset_Mgr_Positions_Long_All`) AS BIGINT)
      - TRY_CAST(TRIM(`Asset_Mgr_Positions_Short_All`) AS BIGINT) AS asset_mgr_net,
    TRY_CAST(TRIM(`Lev_Money_Positions_Long_All`) AS BIGINT)
      - TRY_CAST(TRIM(`Lev_Money_Positions_Short_All`) AS BIGINT) AS lev_money_net,
    TRY_CAST(TRIM(`Other_Rept_Positions_Long_All`) AS BIGINT)
      - TRY_CAST(TRIM(`Other_Rept_Positions_Short_All`) AS BIGINT) AS other_rpt_net,
    TRY_CAST(TRIM(`NonRept_Positions_Long_All`) AS BIGINT)
      - TRY_CAST(TRIM(`NonRept_Positions_Short_All`) AS BIGINT)   AS non_rpt_net,
    (TRY_CAST(TRIM(`Dealer_Positions_Long_All`) AS BIGINT)
      - TRY_CAST(TRIM(`Dealer_Positions_Short_All`) AS BIGINT))
      / NULLIF(TRY_CAST(TRIM(`Open_Interest_All`) AS BIGINT), 0)  AS dealer_pct_oi,
    (TRY_CAST(TRIM(`Asset_Mgr_Positions_Long_All`) AS BIGINT)
      - TRY_CAST(TRIM(`Asset_Mgr_Positions_Short_All`) AS BIGINT))
      / NULLIF(TRY_CAST(TRIM(`Open_Interest_All`) AS BIGINT), 0)  AS asset_mgr_pct_oi,
    (TRY_CAST(TRIM(`Lev_Money_Positions_Long_All`) AS BIGINT)
      - TRY_CAST(TRIM(`Lev_Money_Positions_Short_All`) AS BIGINT))
      / NULLIF(TRY_CAST(TRIM(`Open_Interest_All`) AS BIGINT), 0)  AS lev_money_pct_oi,
    release_ts,
    current_timestamp()                   AS processed_ts
  FROM bootcamp_students.evangoh_capstone.bronze_cftc_fut
  WHERE report_date IS NOT NULL
    AND `CFTC_Contract_Market_Code` IS NOT NULL
    AND release_ts IS NOT NULL
) AS src
ON tgt.report_date = src.report_date
   AND tgt.market_code = src.market_code
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
