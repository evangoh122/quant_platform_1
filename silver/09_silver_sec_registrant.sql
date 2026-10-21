-- silver_sec_registrant: bronze_sec_submissions -> parsed registrant identity
--
-- One row per (cik, payload_sha256) observation.  The bronze table is
-- append-only and MERGE-idempotent on that key; the QUALIFY below also
-- guarantees one row per key if a legacy duplicate ever appears (latest
-- fetched_at wins).
--
-- Source: SEC submissions API (https://data.sec.gov/submissions/).  The
-- payload is the raw JSON text stored by pipelines/ingest_sec_submissions.py.
--   name                  current legal name (as published)
--   sic                   SEC SIC code, kept as a string (leading zeros matter)
--   tickers / exchanges   observations at ingest time (never back-dated)
--   observed_at           the fetch timestamp (fetched_at)
-- Rows with payload IS NULL are HTTP 404 misses and are deliberately excluded.

CREATE OR REPLACE TABLE {catalog}.{schema}.silver_sec_registrant AS
WITH deduped AS (
  SELECT
    cik,
    payload_sha256,
    payload,
    fetched_at,
    ingest_run_id
  FROM {catalog}.{schema}.bronze_sec_submissions
  WHERE payload IS NOT NULL
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY cik, payload_sha256
    ORDER BY fetched_at DESC
  ) = 1
),
parsed AS (
  SELECT
    cik,
    payload_sha256,
    fetched_at,
    ingest_run_id,
    from_json(
      payload,
      'name STRING,
       sic STRING,
       sicDescription STRING,
       tickers ARRAY<STRING>,
       exchanges ARRAY<STRING>,
       stateOfIncorporation STRING,
       fiscalYearEnd STRING,
       entityType STRING'
    ) AS j
  FROM deduped
)
SELECT
  cik                                   AS cik10,
  payload_sha256                        AS payload_sha256,
  j.name                                AS name,
  j.sic                                 AS sic,
  j.sicDescription                      AS sic_description,
  j.tickers                             AS tickers,
  j.exchanges                           AS exchanges,
  j.stateOfIncorporation                AS state_of_incorporation,
  j.fiscalYearEnd                       AS fiscal_year_end,
  j.entityType                          AS entity_type,
  fetched_at                            AS observed_at,
  ingest_run_id                         AS ingest_run_id,
  current_timestamp()                   AS processed_ts
FROM parsed;

-- silver_sec_registrant_former_names: exploded former-name intervals
--
-- One row per (cik, payload_sha256, former name).  The SEC ``from`` / ``to``
-- dates are inclusive and are cast as given — never shifted or adjusted.
-- Also excludes 404 misses (payload IS NULL).

CREATE OR REPLACE TABLE {catalog}.{schema}.silver_sec_registrant_former_names AS
WITH deduped AS (
  SELECT
    cik,
    payload_sha256,
    payload,
    fetched_at,
    ingest_run_id
  FROM {catalog}.{schema}.bronze_sec_submissions
  WHERE payload IS NOT NULL
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY cik, payload_sha256
    ORDER BY fetched_at DESC
  ) = 1
),
parsed AS (
  SELECT
    cik,
    payload_sha256,
    fetched_at,
    ingest_run_id,
    from_json(
      payload,
      'formerNames ARRAY<STRUCT<name:STRING, `from`:STRING, `to`:STRING>>'
    ) AS j
  FROM deduped
)
SELECT
  p.cik                                 AS cik10,
  p.payload_sha256                      AS payload_sha256,
  fn.name                               AS former_name,
  CAST(fn.`from` AS DATE)               AS from_date,
  CAST(fn.`to` AS DATE)                 AS to_date,
  p.fetched_at                          AS observed_at,
  p.ingest_run_id                       AS ingest_run_id,
  current_timestamp()                   AS processed_ts
FROM parsed p
LATERAL VIEW explode(p.j.formerNames) t AS fn;
