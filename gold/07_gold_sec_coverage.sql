-- gold_sec_coverage: SEC filing coverage per ticker.
--
-- One row per ticker in the intended universe (including share-class aliases),
-- left-joined to bronze filings and silver chunks so mapped tickers with zero
-- chunks appear.  Share-class aliases (e.g. GOOG/GOOGL) resolve to the
-- canonical ticker's filing/chunk counts.
--
-- n_filings: distinct chunk-bearing accessions.
-- first_filed / last_filed: min/max accepted_ts (EDGAR acceptance, not filing_date).
-- last_ingest_ts: max bronze ingest_ts.
-- cik: from the latest successful sec_cik_mapping_log entry (mapped status).

CREATE OR REPLACE TABLE {catalog}.{schema}.gold_sec_coverage AS
WITH universe AS (
  SELECT upper(trim(symbol)) AS ticker
  FROM {catalog}.{schema}.gold_tradable_universe
  GROUP BY upper(trim(symbol))
),
-- Canonical ticker per CIK: first alphabetically
canonical AS (
  SELECT
    upper(ticker) AS ticker,
    cik,
    first_value(upper(ticker)) OVER (PARTITION BY cik ORDER BY upper(ticker)) AS canonical_ticker
  FROM (
    SELECT upper(ticker) AS ticker, cik
    FROM {catalog}.{schema}.sec_cik_mapping_log
    WHERE cik IS NOT NULL AND status = 'mapped'
    GROUP BY upper(ticker), cik
  )
),
-- Universe tickers resolved to their canonical ticker for data joins
universe_resolved AS (
  SELECT
    u.ticker,
    coalesce(c.canonical_ticker, u.ticker) AS canonical_ticker,
    coalesce(c.cik, '') AS cik
  FROM universe u
  LEFT JOIN canonical c ON u.ticker = c.ticker
),
filing_agg AS (
  SELECT
    upper(ticker) AS ticker,
    count(DISTINCT accession_number) AS n_filings,
    min(accepted_ts) AS first_filed,
    max(accepted_ts) AS last_filed,
    max(ingest_ts) AS last_ingest_ts
  FROM {catalog}.{schema}.bronze_sec_filings_v2
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
  FROM {catalog}.{schema}.silver_sec_sections
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
      ROW_NUMBER() OVER (PARTITION BY upper(ticker) ORDER BY mapped_ts DESC) AS rn
    FROM {catalog}.{schema}.sec_cik_mapping_log
    WHERE cik IS NOT NULL
      AND status = 'mapped'
  )
  WHERE rn = 1
)
SELECT
  ur.ticker,
  ur.cik,
  coalesce(f.n_filings, 0) AS n_filings,
  coalesce(c.n_chunks, 0) AS n_chunks,
  f.first_filed,
  f.last_filed,
  f.last_ingest_ts
FROM universe_resolved ur
LEFT JOIN filing_agg f ON ur.canonical_ticker = upper(f.ticker)
LEFT JOIN chunk_agg c ON ur.canonical_ticker = upper(c.ticker)
LEFT JOIN latest_mapping lm ON ur.canonical_ticker = upper(lm.ticker)