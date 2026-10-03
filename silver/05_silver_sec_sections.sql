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
-- Source anti-join: only processes accessions absent from silver.

MERGE INTO bootcamp_students.evangoh_capstone.silver_sec_sections AS tgt
USING (
  SELECT
    src.cik,
    src.ticker,
    src.accession_number,
    src.form_type,
    CAST(src.filing_date AS DATE)   AS filing_date,
    src.accepted_ts,
    src.filing_section,
    src.record_key                  AS chunk_id,
    CAST(ROW_NUMBER() OVER (
      PARTITION BY src.accession_number, src.filing_section
      ORDER BY src.record_key
    ) AS INT) - 1                   AS chunk_index,
    src.chunk_text,
    CAST(COALESCE(src.chunk_char_count, length(coalesce(src.chunk_text, ''))) AS INT) AS chunk_char_count,
    src.filing_url                  AS source_url,
    current_timestamp()             AS processed_ts
  FROM bootcamp_students.evangoh_capstone.bronze_sec_filings_v2 src
  LEFT JOIN (
    SELECT DISTINCT accession_number
    FROM bootcamp_students.evangoh_capstone.silver_sec_sections
  ) existing ON src.accession_number = existing.accession_number
  WHERE existing.accession_number IS NULL
    AND src.ticker IN (SELECT symbol FROM universe)
    AND src.filing_section IS NOT NULL
    AND src.filing_section <> 'metadata'
    AND src.filing_section NOT LIKE 'xbrl_fact_%'
    AND src.chunk_text IS NOT NULL
    AND src.cik IS NOT NULL
    AND src.accession_number IS NOT NULL
    AND src.form_type IS NOT NULL
    AND src.accepted_ts IS NOT NULL
) AS src
ON tgt.accession_number = src.accession_number
   AND tgt.filing_section = src.filing_section
   AND tgt.chunk_id = src.chunk_id
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *