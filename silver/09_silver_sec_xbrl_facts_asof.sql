-- silver_sec_xbrl_facts_asof: Point-in-time view of XBRL facts
--
-- Filters silver_sec_xbrl_facts to return only facts that were available
-- at the specified as_of timestamp. For each unique
-- (cik, taxonomy, concept, unit, period) combination, returns the latest
-- value ordered by information_available_ts DESC, filed_date DESC,
-- accession_number DESC.
--
-- Usage:
--   Replace :as_of with the desired timestamp parameter.
--   In Spark SQL: use the Python helper asof_facts() instead.
--
-- This query template is the ONLY selection rule allowed for historical
-- backtests or as-of API requests.

SELECT
  f.cik,
  f.entity_name,
  f.ticker,
  f.taxonomy,
  f.concept,
  f.label,
  f.description,
  f.unit,
  f.value_raw,
  f.value_decimal,
  f.period_start,
  f.period_end,
  f.instant,
  f.fiscal_year,
  f.fiscal_period,
  f.form_type,
  f.accession_number,
  f.filed_date,
  f.frame,
  f.information_available_ts,
  f.first_observed_at,
  f.last_observed_at,
  f.quality_status,
  f.processed_ts
FROM (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY
        cik,
        taxonomy,
        concept,
        unit,
        COALESCE(period_start, ''),
        COALESCE(period_end, ''),
        COALESCE(instant, ''),
        COALESCE(CAST(fiscal_year AS STRING), ''),
        COALESCE(fiscal_period, '')
      ORDER BY
        information_available_ts DESC,
        filed_date DESC,
        accession_number DESC
    ) AS rn
  FROM {catalog}.{schema}.silver_sec_xbrl_facts
  WHERE information_available_ts <= :as_of
    AND quality_status = 'ok'
) f
WHERE f.rn = 1