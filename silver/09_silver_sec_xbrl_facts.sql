-- silver_sec_xbrl_facts: bronze_sec_xbrl_facts -> silver_sec_xbrl_facts
--
-- Normalizes XBRL facts from Company Facts bronze ingestion.
-- Resolves information_available_ts by joining accession_number to
-- bronze_sec_filings_v2.accepted_ts (NEVER filed_date or ingest time).
--
-- Facts whose accession cannot be resolved receive quality_status =
-- 'unresolved_accession' and are kept but excluded from PIT/gold publication.
--
-- Deduplicates repeated ingestions of the same filed fact on the natural key:
--   cik, taxonomy, concept, unit, period_start, period_end/instant,
--   fiscal_year, fiscal_period, form_type, accession_number, frame
-- Keeps the latest successfully parsed bronze observation and preserves
-- first/last observed timestamps. Different accessions are different facts
-- even when concept/unit/period/value match (restatements kept).
--
-- Idempotent: MERGE on the natural composite key with null-safe sentinels.

MERGE INTO {catalog}.{schema}.silver_sec_xbrl_facts AS tgt
USING (
  WITH filings_accepted AS (
    SELECT DISTINCT
      accession_number,
      accepted_ts
    FROM {catalog}.{schema}.bronze_sec_filings_v2
    WHERE accession_number IS NOT NULL
      AND accepted_ts IS NOT NULL
  ),
  deduped_bronze AS (
    SELECT
      b.cik,
      b.entity_name,
      b.ticker,
      b.taxonomy,
      b.concept,
      b.label,
      b.description,
      b.unit,
      b.value_raw,
      b.value_decimal,
      b.period_start,
      b.period_end,
      b.instant,
      b.fiscal_year,
      b.fiscal_period,
      b.form_type,
      b.accession_number,
      b.filed_date,
      b.frame,
      b.payload_hash,
      b.source_updated_at,
      b.ingested_at,
      ROW_NUMBER() OVER (
        PARTITION BY
          b.cik,
          b.taxonomy,
          b.concept,
          b.unit,
          COALESCE(b.period_start, ''),
          COALESCE(b.period_end, ''),
          COALESCE(b.instant, ''),
          COALESCE(CAST(b.fiscal_year AS STRING), ''),
          COALESCE(b.fiscal_period, ''),
          COALESCE(b.form_type, ''),
          b.accession_number,
          COALESCE(b.frame, '')
        ORDER BY b.ingested_at DESC
      ) AS rn,
      MIN(b.ingested_at) OVER (
        PARTITION BY
          b.cik,
          b.taxonomy,
          b.concept,
          b.unit,
          COALESCE(b.period_start, ''),
          COALESCE(b.period_end, ''),
          COALESCE(b.instant, ''),
          COALESCE(CAST(b.fiscal_year AS STRING), ''),
          COALESCE(b.fiscal_period, ''),
          COALESCE(b.form_type, ''),
          b.accession_number,
          COALESCE(b.frame, '')
      ) AS first_observed_at,
      MAX(b.ingested_at) OVER (
        PARTITION BY
          b.cik,
          b.taxonomy,
          b.concept,
          b.unit,
          COALESCE(b.period_start, ''),
          COALESCE(b.period_end, ''),
          COALESCE(b.instant, ''),
          COALESCE(CAST(b.fiscal_year AS STRING), ''),
          COALESCE(b.fiscal_period, ''),
          COALESCE(b.form_type, ''),
          b.accession_number,
          COALESCE(b.frame, '')
      ) AS last_observed_at
    FROM {catalog}.{schema}.bronze_sec_xbrl_facts b
  ),
  normalized AS (
    SELECT
      TRIM(d.cik)                                        AS cik,
      TRIM(d.entity_name)                                AS entity_name,
      UPPER(TRIM(d.ticker))                              AS ticker,
      UPPER(TRIM(d.taxonomy))                            AS taxonomy,
      UPPER(TRIM(d.concept))                             AS concept,
      TRIM(d.label)                                      AS label,
      TRIM(d.description)                                AS description,
      UPPER(TRIM(d.unit))                                AS unit,
      d.value_raw                                        AS value_raw,
      d.value_decimal                                    AS value_decimal,
      d.period_start                                     AS period_start,
      d.period_end                                       AS period_end,
      d.instant                                          AS instant,
      d.fiscal_year                                      AS fiscal_year,
      UPPER(TRIM(d.fiscal_period))                       AS fiscal_period,
      UPPER(TRIM(d.form_type))                           AS form_type,
      TRIM(d.accession_number)                           AS accession_number,
      d.filed_date                                       AS filed_date,
      d.frame                                            AS frame,
      d.payload_hash                                     AS payload_hash,
      d.source_updated_at                                AS source_updated_at,
      d.first_observed_at                                AS first_observed_at,
      d.last_observed_at                                 AS last_observed_at,
      f.accepted_ts                                      AS information_available_ts,
      CASE
        WHEN f.accepted_ts IS NULL THEN 'unresolved_accession'
        ELSE 'ok'
      END                                                AS quality_status,
      current_timestamp()                                AS processed_ts
    FROM deduped_bronze d
    LEFT JOIN filings_accepted f
      ON d.accession_number = f.accession_number
    WHERE d.rn = 1
  )
  SELECT * FROM normalized
) AS src
ON tgt.cik = src.cik
   AND tgt.taxonomy = src.taxonomy
   AND tgt.concept = src.concept
   AND COALESCE(tgt.unit, '') = COALESCE(src.unit, '')
   AND COALESCE(tgt.period_start, '') = COALESCE(src.period_start, '')
   AND COALESCE(tgt.period_end, '') = COALESCE(src.period_end, '')
   AND COALESCE(tgt.instant, '') = COALESCE(src.instant, '')
   AND COALESCE(tgt.fiscal_year, -1) = COALESCE(src.fiscal_year, -1)
   AND COALESCE(tgt.fiscal_period, '') = COALESCE(src.fiscal_period, '')
   AND COALESCE(tgt.form_type, '') = COALESCE(src.form_type, '')
   AND tgt.accession_number = src.accession_number
   AND COALESCE(tgt.frame, '') = COALESCE(src.frame, '')
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *