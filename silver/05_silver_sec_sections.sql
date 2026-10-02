-- silver_sec_sections: bronze_sec_filings_v2 -> silver_sec_sections
--
-- Carries the narrative section text (item1, item1a, item7, item7a, item8, ...).
-- `accepted_ts` is the information-availability timestamp (PIT key) for all SEC
-- features; filing_date is never used for PIT.
--
-- Excludes `metadata` rows (no text) and `xbrl_fact_*` rows (those carry
-- structured facts and belong in silver_sec_entities, not sections).
--
-- chunk_id = record_key (unique per chunk in the source).
-- chunk_index = 0-based order within (accession_number, filing_section).
--
-- Idempotent: MERGE on (accession_number, filing_section, chunk_id).

MERGE INTO bootcamp_students.evangoh_capstone.silver_sec_sections AS tgt
USING (
  SELECT
    cik,
    ticker,
    accession_number,
    form_type,
    CAST(filing_date AS DATE)   AS filing_date,
    accepted_ts,
    filing_section,
    record_key                  AS chunk_id,
    CAST(ROW_NUMBER() OVER (
      PARTITION BY accession_number, filing_section
      ORDER BY chunk_id
    ) AS INT) - 1               AS chunk_index,
    chunk_text,
    CAST(COALESCE(chunk_char_count, length(coalesce(chunk_text, ''))) AS INT) AS chunk_char_count,
    filing_url                  AS source_url,
    current_timestamp()         AS processed_ts
  FROM bootcamp_students.evangoh_capstone.bronze_sec_filings_v2
  WHERE filing_section IS NOT NULL
    AND filing_section <> 'metadata'
    AND filing_section NOT LIKE 'xbrl_fact_%'
    AND chunk_text IS NOT NULL
    AND cik IS NOT NULL
    AND accession_number IS NOT NULL
    AND form_type IS NOT NULL
    AND accepted_ts IS NOT NULL
) AS src
ON tgt.accession_number = src.accession_number
   AND tgt.filing_section = src.filing_section
   AND tgt.chunk_id = src.chunk_id
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
