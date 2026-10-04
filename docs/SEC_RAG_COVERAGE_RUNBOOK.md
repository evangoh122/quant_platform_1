# SEC RAG Coverage Runbook

Operational guide for expanding SEC filing RAG coverage to the full strategy universe.

## Prerequisites

- Databricks workspace access with Unity Catalog permissions
- SEC EDGAR User-Agent configured (see [Secret Setup](#secret-setup) below)
- Bundle target configured (`dev` or `prod`)

## Secret Setup

The pipeline resolves the SEC EDGAR User-Agent in this order:

1. Environment variable `SEC_EDGAR_USER_AGENT`
2. Databricks secret (via `dbutils.secrets.get` on clusters, or SDK on serverless)

Create the secret (never commit the actual value):

```bash
databricks secrets put-secret evangoh_capstone sec_edgar_user_agent
```

When prompted, enter `<app-name> <your real contact email>` (SEC requires a real contact; values containing "example" are rejected).

To verify the secret exists:

```bash
databricks secrets list-secrets evangoh_capstone   # metadata only; shows the key, never the value
```

The `resources/jobs.yml` passes `--user-agent-secret-scope evangoh_capstone` and
`--user-agent-secret-key sec_edgar_user_agent` to the task automatically.

## Environment Setup

```bash
# Optionally set the SEC User-Agent via env (overrides secret if set)
export SEC_EDGAR_USER_AGENT='<your-app-name> your-email@example.com'

# Verify it is set and not a placeholder
test -n "$SEC_EDGAR_USER_AGENT" && echo "OK: User-Agent set" || echo "ERROR: SEC_EDGAR_USER_AGENT not set"
echo "$SEC_EDGAR_USER_AGENT" | grep -qE "@example\.(com|org|net)" && echo "WARNING: Using placeholder domain" || echo "OK: Looks real"
```

## Dry Run

Validate the ingestion plan without fetching any filing bodies:

```bash
databricks bundle validate -t dev
databricks bundle deploy -t dev
databricks bundle run -t dev sec_rag_ingest -- --dry-run --start-date 2024-09-01 --forms 10-K,10-Q --catalog ${catalog} --schema ${schema} --user-agent-secret-scope evangoh_capstone --user-agent-secret-key sec_edgar_user_agent
```

> **Important:** `databricks bundle run <job> -- <args>` sends `<args>` as
> `python_params`, which **replace** the task `parameters` in `resources/jobs.yml`.
> Every command must repeat `--catalog`, `--schema`, `--user-agent-secret-scope`,
> and `--user-agent-secret-key` (or move them to job-level parameters in
> `resources/jobs.yml`).

## Ten-New-Ticker Pilot

Select pilot symbols dynamically — current-universe members with zero chunks:

```sql
SELECT u.symbol
FROM ${catalog}.${schema}.gold_tradable_universe u
LEFT JOIN ${catalog}.${schema}.gold_sec_coverage c ON upper(c.ticker)=upper(u.symbol)
WHERE u.trade_date=(SELECT max(trade_date) FROM ${catalog}.${schema}.gold_tradable_universe)
  AND coalesce(c.n_chunks,0)=0
GROUP BY u.symbol
ORDER BY u.symbol
LIMIT 10;
```

Run the ingestion job with the comma-separated result:

```bash
# Set RUN_ID for traceability
export RUN_ID="pilot-$(date +%Y%m%d_%H%M%S)"

# Ingest pilot tickers
databricks bundle run -t dev sec_rag_ingest -- --tickers "$PILOT_TICKERS" --start-date 2024-09-01 --forms 10-K,10-Q --run-id "$RUN_ID" --catalog ${catalog} --schema ${schema} --user-agent-secret-scope evangoh_capstone --user-agent-secret-key sec_edgar_user_agent

# Refresh silver and coverage
databricks bundle run -t dev silver_gold_refresh

# Build embeddings for pilot tickers
databricks bundle run -t dev sec_embeddings -- --ticker "$PILOT_TICKERS" --batch-size 256 --partitions 4
```

## Verification SQL

Run after pilot and after each full run:

```sql
-- Coverage/counts for target scope
SELECT count(*) AS tickers, sum(n_filings) AS filings, sum(n_chunks) AS chunks,
       min(first_filed), max(last_filed), max(last_ingest_ts)
FROM ${catalog}.${schema}.gold_sec_coverage;

SELECT ticker,n_filings,n_chunks,first_filed,last_filed,last_ingest_ts
FROM ${catalog}.${schema}.gold_sec_coverage
WHERE ticker IN (<quoted pilot tickers>) ORDER BY ticker;

-- Duplicate keys must return zero rows
SELECT record_key,count(*) n FROM ${catalog}.${schema}.bronze_sec_filings_v2
GROUP BY record_key HAVING n>1;
SELECT accession_number,filing_section,chunk_id,count(*) n
FROM ${catalog}.${schema}.silver_sec_sections
GROUP BY accession_number,filing_section,chunk_id HAVING n>1;
SELECT chunk_id,embedding_model,count(*) n
FROM ${catalog}.${schema}.gold_sec_chunk_embeddings
GROUP BY chunk_id,embedding_model HAVING n>1;

-- PIT sanity: accepted time is present, not backfilled from filing date
SELECT count(*) AS null_accepted FROM ${catalog}.${schema}.silver_sec_sections WHERE accepted_ts IS NULL;
-- After-hours filings get the next business day as filing_date, so
-- accepted_ts < filing_date is expected for a small number of rows.
-- A 4-day tolerance rules out legitimate multi-day delays.
SELECT count(*) AS accepted_before_filing
FROM ${catalog}.${schema}.silver_sec_sections
WHERE accepted_ts < cast(filing_date AS timestamp) - INTERVAL 4 DAYS;
SELECT count(*) AS pit_mismatch
FROM ${catalog}.${schema}.silver_sec_sections s
JOIN ${catalog}.${schema}.bronze_sec_filings_v2 b ON s.chunk_id=b.record_key
WHERE unix_timestamp(s.accepted_ts) <> unix_timestamp(b.accepted_ts);

-- Embedding completeness for pilot tickers
SELECT s.ticker,count(*) chunks,count(e.chunk_id) embedded
FROM ${catalog}.${schema}.silver_sec_sections s
LEFT JOIN ${catalog}.${schema}.gold_sec_chunk_embeddings e
  ON s.chunk_id=e.chunk_id AND e.embedding_model='BAAI/bge-small-en-v1.5'
WHERE s.ticker IN (<quoted pilot tickers>) GROUP BY s.ticker;
```

## Retrieval Smoke Test

After pilot, test retrieval for each pilot ticker:

```python
from agent.tools_retrieval import search_sec_filings

# For each pilot ticker — should return results
results = search_sec_filings("AAPL", query="revenue growth", as_of="2025-12-01")
assert len(results) > 0
assert results[0].get("error") is None

# Test a known zero-coverage ticker — should return no_coverage
results = search_sec_filings("XYZNONEXIST", query="test")
assert results[0]["error"] == "no_coverage"
```

## Full Phase 1 Run (Current 300)

```bash
export RUN_ID="phase1-$(date +%Y%m%d_%H%M%S)"

# Ingest all current-universe tickers (phase 1)
databricks bundle run -t dev sec_rag_ingest -- --start-date 2024-09-01 --forms 10-K,10-Q --run-id "$RUN_ID" --catalog ${catalog} --schema ${schema} --user-agent-secret-scope evangoh_capstone --user-agent-secret-key sec_edgar_user_agent

# Refresh silver and coverage
databricks bundle run -t dev silver_gold_refresh

# Build all embeddings
databricks bundle run -t dev sec_embeddings -- --batch-size 256 --partitions 4
```

Re-run all verification SQL and retrieval smoke test.

## Full Phase 2 Run (Historical Members)

```bash
export RUN_ID="phase2-$(date +%Y%m%d_%H%M%S)"

# Ingest with historical universe
databricks bundle run -t dev sec_rag_ingest -- --include-historical --start-date 2024-09-01 --forms 10-K,10-Q --run-id "$RUN_ID" --catalog ${catalog} --schema ${schema} --user-agent-secret-scope evangoh_capstone --user-agent-secret-key sec_edgar_user_agent

# Refresh and rebuild
databricks bundle run -t dev silver_gold_refresh
databricks bundle run -t dev sec_embeddings -- --batch-size 256 --partitions 4
```

## Idempotency Verification

A final identical ingestion rerun must report zero bronze rows appended:

```bash
databricks bundle run -t dev sec_rag_ingest -- --start-date 2024-09-01 --forms 10-K,10-Q --run-id "idempotency-check" --catalog ${catalog} --schema ${schema} --user-agent-secret-scope evangoh_capstone --user-agent-secret-key sec_edgar_user_agent
# Expected: rows_appended = 0
```

**Important:** If the summary reports `rows=unknown` instead of `rows=0`, the idempotency
gate is **NOT** satisfied. `unknown` means one or more MERGE writers could not determine
the inserted row count (DESCRIBE HISTORY returned no metrics). Re-run the ingestion; if
`unknown` persists, investigate the affected filings in `sec_ingest_log` where
`rows_appended IS NULL`.

A final embedding rerun must report zero rows written:

```bash
databricks bundle run -t dev sec_embeddings -- --batch-size 256 --partitions 4
# Expected: rows_written = 0
```

## Troubleshooting

### Missing CIKs
Record missing/ambiguous CIKs from the run summary. These symbols need manual investigation — they may be delisted, renamed, or not SEC-reporting entities.

### Failed Filings
Check the `sec_ingest_log` table for `status = 'failed'` entries:

```sql
SELECT ticker, accession_number, error_code, error_message, attempt
FROM ${catalog}.${schema}.sec_ingest_log
WHERE status = 'failed'
ORDER BY completed_ts DESC
LIMIT 50;
```

### Rate Limiting
The pipeline defaults to 8 requests/second (hard max 10). If you see 429 errors, reduce `SEC_REQUESTS_PER_SECOND`:

```bash
export SEC_REQUESTS_PER_SECOND=6
```

### Embedding Memory
With 350k chunks at 384-d float32, raw vectors are ~0.54 GB. If memory pressure occurs, reduce `--partitions` or `--batch-size`.