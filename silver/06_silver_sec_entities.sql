-- silver_sec_entities: bronze_sec_filings_v2 -> silver_sec_entities
--
-- Extracts four entity types from the source:
--   1. xbrl_fact   : structured XBRL facts (already JSON-encoded in chunk_text
--                    by the upstream ingester; no re-implementation of the
--                    XBRL parser required).
--   2. company     : the registrant's company_name.
--   3. risk_factor : item1a_risk_factors chunks.
--   4. event       : 8-K filings (material event flag source).
--
-- `accepted_ts` is the PIT availability timestamp (never filing_date).
-- source_chunk_id references the source chunk (record_key). XBRL fact chunks
-- live in bronze_sec_filings_v2 rather than silver_sec_sections (sections
-- deliberately excludes xbrl_fact rows), so it is a soft reference.
--
-- Idempotent: MERGE on the natural composite key with null-safe sentinels.
-- Source anti-join: only processes accessions absent from silver.

MERGE INTO bootcamp_students.evangoh_capstone.silver_sec_entities AS tgt
USING (
  -- 1. XBRL facts
  SELECT
    src.cik,
    src.ticker,
    src.accession_number,
    src.form_type,
    src.accepted_ts,
    'xbrl_fact'                                                  AS entity_type,
    get_json_object(src.chunk_text, '$.concept')                 AS entity_key,
    get_json_object(src.chunk_text, '$.value')                   AS entity_value,
    get_json_object(src.chunk_text, '$.unit')                    AS entity_unit,
    CAST(get_json_object(src.chunk_text, '$.period_start') AS DATE)  AS period_start,
    CAST(get_json_object(src.chunk_text, '$.period_end')   AS DATE)  AS period_end,
    1.0                                                          AS confidence,
    src.record_key                                               AS source_chunk_id,
    current_timestamp()                                          AS processed_ts
  FROM bootcamp_students.evangoh_capstone.bronze_sec_filings_v2 src
  LEFT JOIN (
    SELECT DISTINCT accession_number
    FROM bootcamp_students.evangoh_capstone.silver_sec_entities
  ) existing ON src.accession_number = existing.accession_number
  WHERE existing.accession_number IS NULL
    AND src.filing_section LIKE 'xbrl_fact_%'
    AND src.ticker IN (SELECT symbol FROM universe)
    AND src.chunk_text IS NOT NULL
    AND src.cik IS NOT NULL AND src.accession_number IS NOT NULL
    AND src.form_type IS NOT NULL AND src.accepted_ts IS NOT NULL

  UNION ALL

  -- 2. Company entity
  SELECT
    sub.cik,
    sub.ticker,
    sub.accession_number,
    sub.form_type,
    sub.accepted_ts,
    'company'        AS entity_type,
    'company_name'   AS entity_key,
    sub.company_name AS entity_value,
    NULL             AS entity_unit,
    NULL             AS period_start,
    NULL             AS period_end,
    1.0              AS confidence,
    NULL             AS source_chunk_id,
    current_timestamp() AS processed_ts
  FROM (
    SELECT src.cik, src.ticker, src.accession_number, src.form_type, src.accepted_ts, src.company_name,
           ROW_NUMBER() OVER (PARTITION BY src.accession_number ORDER BY src.cik) AS rn
    FROM bootcamp_students.evangoh_capstone.bronze_sec_filings_v2 src
    LEFT JOIN (
      SELECT DISTINCT accession_number
      FROM bootcamp_students.evangoh_capstone.silver_sec_entities
    ) existing ON src.accession_number = existing.accession_number
    WHERE existing.accession_number IS NULL
      AND src.company_name IS NOT NULL
      AND src.ticker IN (SELECT symbol FROM universe)
  ) sub
  WHERE sub.rn = 1

  UNION ALL

  -- 3. Risk-factor entity
  SELECT
    src.cik,
    src.ticker,
    src.accession_number,
    src.form_type,
    src.accepted_ts,
    'risk_factor'                                AS entity_type,
    'item1a'                                     AS entity_key,
    left(src.chunk_text, 200)                    AS entity_value,
    NULL                                         AS entity_unit,
    NULL                                         AS period_start,
    NULL                                         AS period_end,
    0.9                                          AS confidence,
    src.record_key                               AS source_chunk_id,
    current_timestamp()                          AS processed_ts
  FROM bootcamp_students.evangoh_capstone.bronze_sec_filings_v2 src
  LEFT JOIN (
    SELECT DISTINCT accession_number
    FROM bootcamp_students.evangoh_capstone.silver_sec_entities
  ) existing ON src.accession_number = existing.accession_number
  WHERE existing.accession_number IS NULL
    AND src.filing_section = 'item1a_risk_factors'
    AND src.ticker IN (SELECT symbol FROM universe)
    AND src.chunk_text IS NOT NULL
    AND src.cik IS NOT NULL AND src.accession_number IS NOT NULL
    AND src.form_type IS NOT NULL AND src.accepted_ts IS NOT NULL

  UNION ALL

  -- 4. Event entity (one per 8-K filing)
  SELECT
    sub.cik,
    sub.ticker,
    sub.accession_number,
    sub.form_type,
    sub.accepted_ts,
    'event'              AS entity_type,
    '8-K'                AS entity_key,
    'material_event'     AS entity_value,
    NULL                 AS entity_unit,
    NULL                 AS period_start,
    NULL                 AS period_end,
    0.9                  AS confidence,
    NULL                 AS source_chunk_id,
    current_timestamp()  AS processed_ts
  FROM (
    SELECT src.cik, src.ticker, src.accession_number, src.form_type, src.accepted_ts,
           ROW_NUMBER() OVER (PARTITION BY src.accession_number ORDER BY src.cik) AS rn
    FROM bootcamp_students.evangoh_capstone.bronze_sec_filings_v2 src
    LEFT JOIN (
      SELECT DISTINCT accession_number
      FROM bootcamp_students.evangoh_capstone.silver_sec_entities
    ) existing ON src.accession_number = existing.accession_number
    WHERE existing.accession_number IS NULL
      AND src.form_type = '8-K'
      AND src.ticker IN (SELECT symbol FROM universe)
  ) sub
  WHERE sub.rn = 1
) AS src
ON tgt.accession_number = src.accession_number
   AND tgt.entity_type = src.entity_type
   AND COALESCE(tgt.entity_key, '') = COALESCE(src.entity_key, '')
   AND COALESCE(tgt.entity_value, '') = COALESCE(src.entity_value, '')
   AND COALESCE(tgt.period_end, DATE '1900-01-01') = COALESCE(src.period_end, DATE '1900-01-01')
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *