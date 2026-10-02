-- gold_cot_features: silver_cot_positions -> gold_cot_features
--
-- Aggregates to asset-class regime level (mapped_asset x report_date), so
-- multiple contracts of the same regime (e.g. all equity-index futures) are
-- summed. information_available_ts = release_ts (CFTC release time, PIT key).
--
-- Forward-fill semantics: a COT observation is valid from release_ts until the
-- next official release; the AS-OF join in gold_model_features enforces
-- information_available_ts <= prediction_ts, which yields the latest release
-- as-of the prediction timestamp (no backward-fill of future releases).
--
-- 52w metrics are true trailing windows over the 52 reports up to and including
-- the current one:
--   * lev_money_pctile_52w / asset_mgr_pctile_52w are the VALUE percentile
--     (percent_rank semantics: # trailing values strictly below / (n - 1)) over
--     the trailing 52 reports, NOT a rank by report_date. Spark ranking
--     functions (RANK/PERCENT_RANK) cannot take a bounded ROWS frame, so the
--     trailing window is materialised with a self-join on ROW_NUMBER.
--   * lev_money_zscore_52w uses AVG/STDDEV over
--     ROWS BETWEEN 51 PRECEDING AND CURRENT ROW (bounded), not the full
--     expanding history.
-- The first 51 reports of each mapped_asset have a partial window, so their
-- percentile/z-score are NULL (insufficient history), exactly like the options
-- volume_anomaly_zscore's first ~19 days.
--
-- Idempotent: MERGE on (mapped_asset, report_date).

MERGE INTO bootcamp_students.evangoh_capstone.gold_cot_features AS tgt
USING (
  WITH agg AS (
    SELECT
      mapped_asset,
      report_date,
      MAX(release_ts)        AS release_ts,
      SUM(lev_money_net)     AS lev_money_net,
      SUM(asset_mgr_net)     AS asset_mgr_net
    FROM bootcamp_students.evangoh_capstone.silver_cot_positions
    WHERE mapped_asset IS NOT NULL
    GROUP BY mapped_asset, report_date
  ),
  ranked AS (
    SELECT
      mapped_asset,
      report_date,
      release_ts,
      lev_money_net,
      asset_mgr_net,
      ROW_NUMBER() OVER (PARTITION BY mapped_asset ORDER BY report_date) AS rn
    FROM agg
  ),
  win AS (
    SELECT
      mapped_asset,
      report_date,
      release_ts,
      lev_money_net,
      asset_mgr_net,
      lev_money_net - LAG(lev_money_net) OVER (
        PARTITION BY mapped_asset ORDER BY report_date
      ) AS lev_money_net_chg_1w,
      AVG(lev_money_net) OVER (
        PARTITION BY mapped_asset ORDER BY report_date
        ROWS BETWEEN 51 PRECEDING AND CURRENT ROW
      ) AS lev_money_mean_52w,
      STDDEV(lev_money_net) OVER (
        PARTITION BY mapped_asset ORDER BY report_date
        ROWS BETWEEN 51 PRECEDING AND CURRENT ROW
      ) AS lev_money_std_52w,
      AVG(asset_mgr_net) OVER (
        PARTITION BY mapped_asset ORDER BY report_date
        ROWS BETWEEN 51 PRECEDING AND CURRENT ROW
      ) AS asset_mgr_mean_52w,
      STDDEV(asset_mgr_net) OVER (
        PARTITION BY mapped_asset ORDER BY report_date
        ROWS BETWEEN 51 PRECEDING AND CURRENT ROW
      ) AS asset_mgr_std_52w
    FROM ranked
  ),
  pct AS (
    SELECT
      a.mapped_asset,
      a.report_date,
      1.0 * SUM(CASE WHEN b.lev_money_net < a.lev_money_net THEN 1 ELSE 0 END)
            / NULLIF(COUNT(*) - 1, 0) AS lev_money_pctile_52w,
      1.0 * SUM(CASE WHEN b.asset_mgr_net < a.asset_mgr_net THEN 1 ELSE 0 END)
            / NULLIF(COUNT(*) - 1, 0) AS asset_mgr_pctile_52w
    FROM ranked a
    JOIN ranked b
      ON b.mapped_asset = a.mapped_asset
     AND b.rn BETWEEN a.rn - 51 AND a.rn
    GROUP BY a.mapped_asset, a.report_date
  ),
  feats AS (
    SELECT
      w.mapped_asset,
      w.report_date,
      w.release_ts,
      w.lev_money_net,
      w.lev_money_net_chg_1w,
      p.lev_money_pctile_52w,
      (w.lev_money_net - w.lev_money_mean_52w) / NULLIF(w.lev_money_std_52w, 0)
        AS lev_money_zscore_52w,
      w.asset_mgr_net,
      p.asset_mgr_pctile_52w,
      (w.asset_mgr_net - w.asset_mgr_mean_52w) / NULLIF(w.asset_mgr_std_52w, 0)
        AS asset_mgr_zscore_52w
    FROM win w
    JOIN pct p
      ON p.mapped_asset = w.mapped_asset AND p.report_date = w.report_date
  )
  SELECT
    mapped_asset,
    report_date,
    release_ts AS information_available_ts,
    lev_money_net,
    lev_money_net_chg_1w,
    lev_money_pctile_52w,
    lev_money_zscore_52w,
    asset_mgr_net,
    asset_mgr_pctile_52w,
    (lev_money_zscore_52w + asset_mgr_zscore_52w) / 2.0 AS crowding_score,
    CASE
      WHEN lev_money_zscore_52w > 0.5  THEN 'risk_on'
      WHEN lev_money_zscore_52w < -0.5 THEN 'risk_off'
      ELSE 'neutral'
    END AS regime_label,
    current_timestamp() AS processed_ts
  FROM feats
) AS src
ON tgt.mapped_asset = src.mapped_asset AND tgt.report_date = src.report_date
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
