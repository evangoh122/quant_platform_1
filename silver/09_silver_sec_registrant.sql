-- silver_sec_registrant: bronze_sec_submissions -> parsed registrant identity
--
-- Grain: one row per (cik10, payload_sha256), i.e. one row per distinct fetched
-- payload.  A CIK therefore gains another row whenever its submissions document
-- changes — many rows per CIK by design, which is the identity history.
-- ``is_latest`` is TRUE on the row with the newest observed_at per cik10
-- (payload_sha256 breaks ties): filter it for the current attributes and use
-- observed_at as-of for historical questions.
--
-- The bronze table is append-only and MERGE-idempotent on that key; the QUALIFY
-- below also guarantees one row per key if a legacy duplicate ever appears
-- (latest fetched_at wins).
--
-- Source: SEC submissions API (https://data.sec.gov/submissions/).  The
-- payload is the raw JSON text stored by pipelines/ingest_sec_submissions.py.
--   name                  current legal name (as published)
--   sic                   SEC SIC code, kept as a string (leading zeros matter)
--   tickers / exchanges   observations at ingest time (never back-dated)
--   observed_at           the fetch timestamp (fetched_at)
--   data_source           always 'sec_edgar' (config/data_sources.py)
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
),
projected AS (
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
    'sec_edgar'                           AS data_source,
    current_timestamp()                   AS processed_ts
  FROM parsed
)
SELECT
  p.cik10,
  p.payload_sha256,
  p.name,
  p.sic,
  p.sic_description,
  p.tickers,
  p.exchanges,
  p.state_of_incorporation,
  p.fiscal_year_end,
  p.entity_type,
  p.observed_at,
  p.ingest_run_id,
  p.data_source,
  p.processed_ts,
  ROW_NUMBER() OVER (
    PARTITION BY p.cik10
    ORDER BY p.observed_at DESC, p.payload_sha256 DESC
  ) = 1                                   AS is_latest
FROM projected p;

ALTER TABLE {catalog}.{schema}.silver_sec_registrant
  ALTER COLUMN data_source COMMENT 'Provider code from config.data_sources.DATA_SOURCES — this table is always sec_edgar';

ALTER TABLE {catalog}.{schema}.silver_sec_registrant
  ALTER COLUMN data_source SET NOT NULL;

-- silver_sec_registrant_former_names: exploded former-name intervals
--
-- Grain: one row per (cik10, payload_sha256, former_name, from_date).  A
-- registrant can reuse a name across two periods (A -> B -> A), so from_date is
-- part of the key: the same former name published for two periods yields two
-- rows and is never collapsed into one.
--
-- The SEC publishes formerNames[].from / .to as ISO-8601 midnight-UTC
-- timestamps ("2001-04-02T00:00:00.000Z").  The expressions below take the
-- published calendar date, substring(..., 1, 10), and keep the SEC's inclusive
-- bounds exactly — never shifted by a day or made exclusive.
--
-- try_to_date, not to_date: under ANSI mode a bare to_date raises on a string
-- it cannot parse, and one malformed SEC value would then abort the whole
-- shared silver refresh.  try_to_date returns NULL instead, so a published
-- value that is not a calendar date lands as NULL — meaning "the published
-- value is not a date", never "the interval has no date".  The pure parser
-- (sec_kg/submissions.py, _sec_date) keeps the same published-calendar-date
-- rule, i.e. ISO-8601 timestamps are date-truncated and the bounds stay
-- inclusive, but it keeps a non-ISO value verbatim on the Python record.  A
-- DATE column cannot hold that text, so NULL is the documented projection of
-- "unparseable" here.
--
-- Also excludes 404 misses (payload IS NULL).  data_source is always
-- 'sec_edgar', from the controlled vocabulary in config/data_sources.py.

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
),
exploded AS (
  SELECT
    p.cik                                    AS cik,
    p.payload_sha256                         AS payload_sha256,
    p.fetched_at                             AS fetched_at,
    p.ingest_run_id                          AS ingest_run_id,
    fn.name                                  AS former_name,
    try_to_date(substring(fn.`from`, 1, 10)) AS from_date,
    try_to_date(substring(fn.`to`, 1, 10))   AS to_date
  FROM parsed p
  LATERAL VIEW explode(p.j.formerNames) t AS fn
)
SELECT
  e.cik                                     AS cik10,
  e.payload_sha256                          AS payload_sha256,
  e.former_name                             AS former_name,
  e.from_date                               AS from_date,
  e.to_date                                 AS to_date,
  e.fetched_at                              AS observed_at,
  e.ingest_run_id                           AS ingest_run_id,
  'sec_edgar'                               AS data_source,
  current_timestamp()                       AS processed_ts
FROM exploded e
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY e.cik, e.payload_sha256, e.former_name, e.from_date
  ORDER BY e.fetched_at DESC
) = 1;

ALTER TABLE {catalog}.{schema}.silver_sec_registrant_former_names
  ALTER COLUMN data_source COMMENT 'Provider code from config.data_sources.DATA_SOURCES — this table is always sec_edgar';

ALTER TABLE {catalog}.{schema}.silver_sec_registrant_former_names
  ALTER COLUMN data_source SET NOT NULL;
