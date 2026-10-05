### api/services/xbrl_client.py:30
_🩺 Stability & Availability_ | _🟡 Minor_ | _⚡ Quick win_



### docs/SEC_RAG_COVERAGE_RUNBOOK.md:53
_🎯 Functional Correctness_ | _🟡 Minor_ | _⚡ Quick win_

**Fix: Arguments after `--` replace the job's `--catalog`, `--schema` and secret parameters.**

With `databricks bundle run <job> -- <args>`, the CLI sends the arguments as `python_params`. These override the task `parameters` in `resources/jobs.yml`; they are not appended. Each `sec_rag_ingest` and `sec_embeddings` command in this runbook therefore runs with the defaults in `main()`: `bootcamp_students` / `evangoh_capstone`, not `${var.catalog}` / `${var.schema}`. For any target whose schema differs, the ingest writes to the wrong schema. `silver_gold_refresh` then reads the target schema. Repeat the catalog, schema and secret arguments in every command, or move them to job-level parameters.



### docs/SEC_RAG_COVERAGE_RUNBOOK.md:115
_🎯 Functional Correctness_ | _🟡 Minor_ | _⚡ Quick win_

**Fix: `accepted_before_filing` flags valid after-hours filings.**

EDGAR gives the next business day's filing date to submissions accepted after the daily cutoff (17:30 ET). For those filings `accepted_ts < cast(filing_date AS timestamp)` is expected. This check therefore reports non-zero rows on correct data. Operators may treat the result as a PIT failure. Bound the check to a meaningful tolerance, for example `accepted_ts < cast(filing_date AS timestamp) - INTERVAL 4 DAYS`, or document that a non-zero count is expected.



### evals/rag_eval/corpus.py:462
_🎯 Functional Correctness_ | _🟠 Major_ | _⚡ Quick win_



### gold/07_gold_sec_coverage.sql:16
_🗄️ Data Integrity & Integration_ | _🟠 Major_ | _⚡ Quick win_



### notebooks/refresh_bronze_cot.py:75
_🎯 Functional Correctness_ | _🟡 Minor_ | _⚡ Quick win_

**Reject placeholder addresses without rejecting valid contact addresses.**

If `CFTC_USER_EMAIL` is `analyst@myexample.org`, the substring check raises `ValueError` and blocks every download. Check for a placeholder domain or address instead of any occurrence of `example`.



### pipelines/sec_rag_ingest.py:878
_🗄️ Data Integrity & Integration_ | _🟠 Major_ | _⚡ Quick win_

**Fix: SEC history files are not nested under `filings.recent`, so they are always skipped.**

The overflow files listed in `filings.files` (for example `CIK0001045810-submissions-001.json`) store `accessionNumber`, `filingDate`, `form`, `primaryDocument` and `acceptanceDateTime` as top-level arrays. Only the main `CIK##########.json` wraps them in `filings.recent`. Line 867 reads `hist_data.get("filings", {}).get("recent", {})`. For a real history file this returns `{}`, and the loop continues at line 869.

- Frequent filers (banks, insurers, issuers with many 424B/8-K filings) can push 10-K/10-Q filings from after `start_date` out of the `recent` window.
- Those filings are never discovered.
- The ticker is not marked partial, because the fetch succeeded.
- The fixture `tests/rag/fixtures/sec/submissions_history.json` uses 

### pipelines/sec_rag_ingest.py:1396
_🗄️ Data Integrity & Integration_ | _🟠 Major_ | _🏗️ Heavy lift_

**Fix: Share classes with one CIK never get their own chunks.**

GOOG/GOOGL, FOX/FOXA and NWS/NWSA map to the same CIK, so they discover the same accessions.

- **First run:** both tickers plan the same filing. `SparkDataWriter` merges on `accession_number` only (line 1778). The second writer inserts 0 rows, and its log entry still reports `succeeded`.
- **Later runs:** the accession is already in `existing_accessions` with the same CIK. The second ticker is counted as `skipped_existing`.
- **Result:** bronze, silver and `gold_sec_coverage` hold rows for only one class. `check_ticker_coverage("GOOGL")` raises `NoCoverageError` permanently, and the runbook gate cannot detect this.

Choose one model and apply it consistently:
- Write per ticker and key the MERGE and the anti-join on `(ticker, accession_number)`.
- Or resolve 

