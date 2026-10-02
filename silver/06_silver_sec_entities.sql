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

MERGE INTO bootcamp_students.evangoh_capstone.silver_sec_entities AS tgt
USING (
  -- 1. XBRL facts
  SELECT
    cik,
    ticker,
    accession_number,
    form_type,
    accepted_ts,
    'xbrl_fact'                                                  AS entity_type,
    get_json_object(chunk_text, '$.concept')                     AS entity_key,
    get_json_object(chunk_text, '$.value')                       AS entity_value,
    get_json_object(chunk_text, '$.unit')                        AS entity_unit,
    CAST(get_json_object(chunk_text, '$.period_start') AS DATE)  AS period_start,
    CAST(get_json_object(chunk_text, '$.period_end')   AS DATE)  AS period_end,
    1.0                                                          AS confidence,
    record_key                                                   AS source_chunk_id,
    current_timestamp()                                          AS processed_ts
  FROM bootcamp_students.evangoh_capstone.bronze_sec_filings_v2
  WHERE filing_section LIKE 'xbrl_fact_%'
    AND chunk_text IS NOT NULL
    AND cik IS NOT NULL AND accession_number IS NOT NULL
    AND form_type IS NOT NULL AND accepted_ts IS NOT NULL

  UNION ALL

  -- 2. Company entity
  SELECT
    cik,
    ticker,
    accession_number,
    form_type,
    accepted_ts,
    'company'        AS entity_type,
    'company_name'   AS entity_key,
    company_name     AS entity_value,
    NULL             AS entity_unit,
    NULL             AS period_start,
    NULL             AS period_end,
    1.0              AS confidence,
    NULL             AS source_chunk_id,
    current_timestamp() AS processed_ts
  FROM (
    SELECT cik, ticker, accession_number, form_type, accepted_ts, company_name,
           ROW_NUMBER() OVER (PARTITION BY accession_number ORDER BY cik) AS rn
    FROM bootcamp_students.evangoh_capstone.bronze_sec_filings_v2
    WHERE company_name IS NOT NULL
  )
  WHERE rn = 1

  UNION ALL

  -- 3. Risk-factor entity
  SELECT
    cik,
    ticker,
    accession_number,
    form_type,
    accepted_ts,
    'risk_factor'                                AS entity_type,
    'item1a'                                     AS entity_key,
    left(chunk_text, 200)                        AS entity_value,
    NULL                                         AS entity_unit,
    NULL                                         AS period_start,
    NULL                                         AS period_end,
    0.9                                          AS confidence,
    record_key                                   AS source_chunk_id,
    current_timestamp()                          AS processed_ts
  FROM bootcamp_students.evangoh_capstone.bronze_sec_filings_v2
  WHERE filing_section = 'item1a_risk_factors'
    AND chunk_text IS NOT NULL
    AND cik IS NOT NULL AND accession_number IS NOT NULL
    AND form_type IS NOT NULL AND accepted_ts IS NOT NULL

  UNION ALL

  -- 4. Event entity (one per 8-K filing)
  SELECT
    cik,
    ticker,
    accession_number,
    form_type,
    accepted_ts,
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
    SELECT cik, ticker, accession_number, form_type, accepted_ts,
           ROW_NUMBER() OVER (PARTITION BY accession_number ORDER BY cik) AS rn
    FROM bootcamp_students.evangoh_capstone.bronze_sec_filings_v2
    WHERE form_type = '8-K'
  )
  WHERE rn = 1
) AS src
ON tgt.accession_number = src.accession_number
   AND tgt.entity_type = src.entity_type
   AND COALESCE(tgt.entity_key, '') = COALESCE(src.entity_key, '')
   AND COALESCE(tgt.entity_value, '') = COALESCE(src.entity_value, '')
   AND COALESCE(tgt.period_end, DATE '1900-01-01') = COALESCE(src.period_end, DATE '1900-01-01')
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
