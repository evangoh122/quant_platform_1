# BUILD rag-coverage round 6 (builder: MiMo; checker: Claude Sonnet subagent; reviewer: dataexpert Claude)

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/rag-coverage. Commit after each item with descriptive
messages. NEVER delete or weaken existing tests (item 1 replaces a legacy notebook — that is allowed and intended).
Checker verdict: .agents/deepseek/VERDICT-rag-coverage-round5.md (CHANGES_REQUESTED). Items 1, 4, 6, 7 passed.

## 1 (blocking). Legacy notebook → thin wrapper (Claude's decision)
notebooks/02_ingest_sec_edgar.py (3,683 lines) is a legacy 16–40-ticker ingester with its own UA and ingestion code.
The job (resources/jobs.yml `sec_rag_ingest`) already runs pipelines/sec_rag_ingest.py. Replace the notebook body with a
thin Databricks wrapper (< ~80 lines):
- dbutils widgets mirroring the pipeline CLI (tickers, start_date, forms, dry_run, include_historical, run_id), read via
  `globals().get("dbutils")`; build an argv list and call `pipelines.sec_rag_ingest.main(argv)` (make main accept argv if it doesn't).
- sys.path set up for the repo root like other notebooks; NO User-Agent, NO requests/BeautifulSoup, NO own ingestion code.
- A header comment: legacy implementation removed in favour of the pipeline; see git history (cite the last commit containing it).
- Update docs/MERGE_PLAN.md:38 (and any other doc that says to run 02_ingest_sec_edgar for ingestion) to point at the
  `sec_rag_ingest` job / runbook.
Tests: the notebook file contains no "User-Agent", "requests.get", "BeautifulSoup"; executing it with a fake dbutils
(widgets) and a monkeypatched `pipelines.sec_rag_ingest.main` passes the expected argv (dry_run → "--dry-run" etc.).
Check no other code imports functions from the old notebook (grep) before deleting.

## 2 (blocking). CIK mapping log writer
`SparkCikMappingLogWriter` calls `createDataFrame([row])` with no schema, one table write per ticker; a row with cik=None
(missing ticker) cannot be type-inferred and will raise in production.
- Explicit StructType matching docs/DATA_SCHEMAS.md (and any DDL) exactly, nullable cik.
- Batch: collect rows and write once per run (or per bounded chunk), not per ticker.
- Tests with fake Spark: schema passed equals the documented schema (names, types, nullability); a cik=None row is
  written fine; N tickers → 1 write call. Mutation proofs (in /tmp copy, paste output): drop the schema → test FAILS;
  per-ticker writes → test FAILS.

## 3. Strengthen main() write-mode test
Assert exact row CONTENT (ticker, cik, accession, form, accepted_ts/information_available_ts, chunk ids/count) written to
the filings/chunks writers and sec_ingest_log, and the exact entries given to the CIK mapping log writer — not only counts.

## 4. Pre-existing COT test interaction (investigate, fix if small)
Running `pytest tests/rag tests/bronze` together makes 6 tests in tests/bronze/test_refresh_bronze_cot.py::TestIdempotency
fail (they pass alone; same on base 4db30fa). Likely a test-isolation leak (module state, env var such as CFTC_USER_EMAIL,
or sys.modules fakes from tests/rag). Find the cause; fix the isolation (fixture cleanup/monkeypatch), not the assertions.
If it's not caused by this branch's files and the fix is outside scope, document the root cause in your verdict.

## Acceptance
- python -m pytest tests/rag tests/bronze -q (COMBINED) all pass; pyspark hidden
  (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps) tests/rag all pass.
- .agents/mimo/VERDICT-rag-coverage-round6.md with counts + mutation outputs. Commit everything.
