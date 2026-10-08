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
  -- Primary universe from gold_tradable_universe
  SELECT upper(trim(symbol)) AS ticker
  FROM {catalog}.{schema}.gold_tradable_universe
  GROUP BY upper(trim(symbol))
  UNION
  -- Include tickers that have silver chunks but are absent from
  -- gold_tradable_universe (e.g. newly ingested SEC tickers)
  SELECT DISTINCT upper(ticker) AS ticker
  FROM {catalog}.{schema}.silver_sec_sections
  WHERE ticker IS NOT NULL
),
latest_mapping AS (
  -- Latest CIK per ticker (by mapped_ts)
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
),
-- Per-ticker chunk counts from silver (used to pick the canonical ticker)
ticker_chunk_counts AS (
  SELECT
    upper(ticker) AS ticker,
    count(*) AS n_chunks
  FROM {catalog}.{schema}.silver_sec_sections
  GROUP BY upper(ticker)
),
-- Canonical ticker per CIK: the ticker holding the most chunks; tie → alphabetical
canonical_per_cik AS (
  SELECT
    lm.cik,
    lm.ticker AS canonical_ticker
  FROM latest_mapping lm
  LEFT JOIN ticker_chunk_counts tcc ON lm.ticker = tcc.ticker
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY lm.cik
    ORDER BY coalesce(tcc.n_chunks, 0) DESC, lm.ticker ASC
  ) = 1
),
-- Universe tickers resolved to their canonical ticker for data joins
universe_resolved AS (
  SELECT
    u.ticker,
    coalesce(cpc.canonical_ticker, u.ticker) AS canonical_ticker,
    coalesce(lm.cik, '') AS cik
  FROM universe u
  LEFT JOIN latest_mapping lm ON u.ticker = lm.ticker
  LEFT JOIN canonical_per_cik cpc ON lm.cik = cpc.cik
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
)
SELECT
  ur.ticker,
  ur.cik,
  ur.canonical_ticker,
  coalesce(f.n_filings, 0) AS n_filings,
  coalesce(c.n_chunks, 0) AS n_chunks,
  f.first_filed,
  f.last_filed,
  f.last_ingest_ts
FROM universe_resolved ur
LEFT JOIN filing_agg f ON ur.canonical_ticker = upper(f.ticker)
LEFT JOIN chunk_agg c ON ur.canonical_ticker = upper(c.ticker)