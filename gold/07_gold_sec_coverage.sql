-- gold_sec_coverage: SEC filing coverage per ticker.
--
-- One row per canonical ticker in the intended universe, left-joined to
-- bronze filings and silver chunks so mapped tickers with zero chunks appear.
--
-- n_filings: distinct chunk-bearing accessions.
-- first_filed / last_filed: min/max accepted_ts (EDGAR acceptance, not filing_date).
-- last_ingest_ts: max bronze ingest_ts.

CREATE OR REPLACE TABLE bootcamp_students.evangoh_capstone.gold_sec_coverage AS
WITH universe AS (
  SELECT upper(trim(symbol)) AS ticker
  FROM bootcamp_students.evangoh_capstone.gold_tradable_universe
  GROUP BY upper(trim(symbol))
),
filing_agg AS (
  SELECT
    upper(ticker) AS ticker,
    count(DISTINCT accession_number) AS n_filings,
    min(accepted_ts) AS first_filed,
    max(accepted_ts) AS last_filed,
    max(ingest_ts) AS last_ingest_ts
  FROM bootcamp_students.evangoh_capstone.bronze_sec_filings_v2
  WHERE filing_section IS NOT NULL
    AND filing_section <> 'metadata'
    AND filing_section NOT LIKE 'xbrl_fact_%'
    AND chunk_text IS NOT NULL
  GROUP BY upper(ticker)
),
chunk_agg AS (
  SELECT
    upper(ticker) AS ticker,
    count(*) AS n_chunks
  FROM bootcamp_students.evangoh_capstone.silver_sec_sections
  GROUP BY upper(ticker)
),
latest_mapping AS (
  SELECT
    upper(ticker) AS ticker,
    cik
  FROM (
    SELECT
      upper(ticker) AS ticker,
      cik,
      ROW_NUMBER() OVER (PARTITION BY upper(ticker) ORDER BY ingest_ts DESC) AS rn
    FROM bootcamp_students.evangoh_capstone.bronze_sec_filings_v2
    WHERE cik IS NOT NULL
  )
  WHERE rn = 1
)
SELECT
  coalesce(u.ticker, f.ticker, c.ticker) AS ticker,
  coalesce(lm.cik, '') AS cik,
  coalesce(f.n_filings, 0) AS n_filings,
  coalesce(c.n_chunks, 0) AS n_chunks,
  f.first_filed,
  f.last_filed,
  f.last_ingest_ts
FROM universe u
FULL OUTER JOIN filing_agg f ON upper(u.ticker) = upper(f.ticker)
FULL OUTER JOIN chunk_agg c ON upper(coalesce(u.ticker, f.ticker)) = upper(c.ticker)
LEFT JOIN latest_mapping lm ON upper(coalesce(u.ticker, f.ticker)) = upper(lm.ticker)