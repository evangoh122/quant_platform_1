-- silver_sec_xbrl_facts DDL: CREATE TABLE IF NOT EXISTS
--
-- Run BEFORE the MERGE in 09_silver_sec_xbrl_facts.sql.
-- Every column the MERGE INSERT/UPDATE writes is listed here with explicit types.
-- NOT NULL only where the source expression can never be NULL (window aggregates,
-- CASE with ELSE, current_timestamp). Nullable columns match the MERGE source
-- which may produce NULLs (e.g. TRIM of a NULL bronze column, LEFT JOIN result).

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.silver_sec_xbrl_facts (
    cik                       STRING,
    entity_name               STRING,
    ticker                    STRING,
    taxonomy                  STRING,
    concept                   STRING,
    label                     STRING,
    description               STRING,
    unit                      STRING,
    value_raw                 STRING,
    value_decimal             DOUBLE,
    period_start              STRING,
    period_end                STRING,
    instant                   STRING,
    fiscal_year               INT,
    fiscal_period             STRING,
    form_type                 STRING,
    accession_number          STRING,
    filed_date                STRING,
    frame                     STRING,
    payload_hash              STRING,
    source_updated_at         STRING,
    first_observed_at         TIMESTAMP NOT NULL,
    last_observed_at          TIMESTAMP NOT NULL,
    information_available_ts  TIMESTAMP,
    quality_status            STRING    NOT NULL,
    processed_ts              TIMESTAMP NOT NULL
) USING DELTA