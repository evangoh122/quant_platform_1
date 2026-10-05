> **EXECUTION ORDER (Claude, 2026-10-03):** IMPLEMENT THIS SPEC NOW, end to end. Do NOT stop to ask
> "Shall I proceed?". The previous run only produced a plan. Write the code and the tests, run the
> acceptance commands, commit, and write the verdict. If something is ambiguous, choose the
> option most consistent with the spec, record it in the verdict, and continue.

# BUILD: SEC RAG coverage for the strategy universe

## Purpose and fixed decisions

Extend the SEC filing RAG corpus from the current semiconductor subset to the strategy universe. Phase 1 is the 300 symbols on the latest `trade_date` in `gold_tradable_universe`; Phase 2 is the remaining historical members (currently 557 distinct total). Only 10-K and 10-Q filings with `filing_date >= 2024-09-01` are in scope. Retrieval must remain local BM25 + dense retrieval; do not add Databricks Vector Search.

Use `bootcamp_students.evangoh_capstone.bronze_sec_filings_v2`, not `bronze_sec_filings`. The v2 table is the source already consumed by `silver/05_silver_sec_sections.sql` and `silver/06_silver_sec_entities.sql`, contains `accepted_ts`, deterministic `record_key`, chunk fields, and already has 25 tickers/72,970 rows. The legacy table has a different 19-column schema and switching would split the lineage that produced today's 10,720 silver chunks. Preserve the 17-column v2 schema for chunk rows. Metadata-only rows are permitted but ingestion idempotency is by filing accession, not merely by row key.

When this spec says append-only, it means existing bronze facts/chunks are never updated or deleted. A rerun anti-joins completed accessions and appends zero data rows. Operational log rows are an audit trail and may add a new attempt row on each run.

## 1. Extract one offline-testable EDGAR lane

1. Add `pipelines/sec_rag_ingest.py` as the production CLI and pure/core implementation. Do not import `pyspark`, `delta`, `databricks`, or create a Spark session at module import time. Put those imports behind the Databricks adapter/CLI boundary so all pure tests run with `pyspark` and `databricks.connect` hidden. Use dependency injection protocols for the HTTP client, clock/sleeper, universe reader, existing-accession reader, data writer, and ingest-log writer.
2. Refactor (do not semantically rewrite) the established parsing code from `notebooks/02_ingest_sec_edgar.py:1835-1875` (`_record_key`, `_parse_sec_timestamp`), `:2848-2879` (`SECTION_PATTERNS`), `:2882-2920` (`_strip_html`), `:2923-2969` (`_chunk_text`), `:2972-3058` (filing-document fallback), and `:3243-3394` (section extraction, caps, fallback, chunk enumeration and key inputs) into importable functions in `pipelines/sec_rag_ingest.py`. The notebook must import/call these functions; there must be exactly one production definition of each rule after the change.
3. Preserve the existing behavior byte-for-byte for parity: remove script/style/noscript/table, normalize whitespace, remove “Table of Contents”, use the existing ordered regex patterns, 50,000-character section cap, `full_document` 100,000-character fallback, existing `DEFAULT_CHUNK_SIZE` and `DEFAULT_CHUNK_OVERLAP`, minimum 50 characters, 1-based chunk ordinal, and `record_key = sha256("rag_chunk||{ticker}||{accession}||{section_name}||{chunk_idx}")`. Do not put mutable text, CIK, filing date, or ingest time in the key. The bronze integer `chunk_id` remains the ordinal; silver continues to use `record_key` as its stable string `chunk_id` (`silver/05_silver_sec_sections.sql:10,25`).
4. Turn `notebooks/02_ingest_sec_edgar.py` into a thin Databricks entry point for this lane or add a final cell that invokes the new CLI functions. Remove/disable the hard-coded `UNIVERSE_STK` execution path at `:1620-1650` and the `max_filings_per_ticker=8` truncation at `:3061-3065,3163-3191`; the cutoff and forms define completeness.

### Universe selection and ticker-to-CIK mapping

5. Query symbols with this deterministic ordering and phase label:

   ```sql
   WITH latest AS (SELECT max(trade_date) AS d FROM ${catalog}.${schema}.gold_tradable_universe),
   ranked AS (
     SELECT upper(trim(symbol)) AS ticker, 1 AS phase
     FROM ${catalog}.${schema}.gold_tradable_universe, latest
     WHERE trade_date = latest.d
     UNION
     SELECT upper(trim(symbol)) AS ticker, 2 AS phase
     FROM ${catalog}.${schema}.gold_tradable_universe
   )
   SELECT ticker, min(phase) AS phase FROM ranked GROUP BY ticker ORDER BY phase, ticker
   ```

   Default CLI behavior is phase 1/current 300. `--include-historical` adds phase 2. `--tickers AAPL,MSFT` is an explicit pilot override and must still run mapping and logging.
6. Implement `normalize_sec_ticker(symbol)` and `build_cik_map(symbols, company_tickers_payload)`. Canonical application tickers are uppercase and preserve the universe spelling. For SEC lookup, normalize whitespace/case and treat `.` and `-` as equivalent class-share separators: try exact spelling first, then `BRK-B`/`BRK.B` aliases in both directions. Build the reverse map from cached SEC `https://www.sec.gov/files/company_tickers.json`; CIKs are zero-padded to 10 digits. Do not invent a CIK from a ticker, and do not map ambiguous aliases.
7. Cache the raw ticker JSON at a configurable DBFS/workspace path (`SEC_COMPANY_TICKERS_CACHE`, default `/Volumes/${catalog}/${schema}/sec_cache/company_tickers.json`) with fetched timestamp/ETag sidecar. Default TTL is 24 hours (`SEC_TICKER_CACHE_TTL_SECONDS=86400`). A valid stale cache is an allowed fallback after a fetch failure and must emit a warning; malformed cache/network payload fails mapping safely. `--refresh-cik-cache` forces refresh. Tests use fixture bytes and a fake cache—never network.
8. Emit one structured mapping result for every input: `ticker`, `lookup_symbol`, `cik`, `status` (`mapped|missing|ambiguous`), `reason`, `mapped_ts`. Append it to `${catalog}.${schema}.bronze_sec_cik_mapping_log`. Missing, delisted, renamed, non-SEC, and ambiguous symbols are warning/error counts in the run summary and are never silently removed. A missing CIK skips SEC calls for that symbol but still records the mapping and run result. Historical/delisted symbols may resolve from the cached SEC file; optionally accept an explicit config override file, but every override must identify its source and must not contain secrets.

### HTTP, filing discovery, PIT, idempotency and resume

9. Replace the placeholder user agent behavior in `etl/extract_edgar.py:27-43` and notebook `:1682-1700` for this lane. Require `SEC_EDGAR_USER_AGENT` (descriptive application/contact string) from environment or Databricks secret-backed task environment; fail before any request if absent or still a placeholder. Never log the whole value. Do not commit a contact string or secret.
10. Implement one process-wide, thread-safe token-bucket/sliding-window limiter shared by every SEC hostname request, including JSON, submission-history pages, primary documents, and archive-index fallbacks. It must guarantee no more than 10 request starts in any rolling one-second window; configure `SEC_REQUESTS_PER_SECOND` with default 8 and hard reject values over 10. Inject monotonic clock and sleep for deterministic tests.
11. Centralize requests in `SecClient`. On 429 and 503, honor numeric or HTTP-date `Retry-After`, otherwise use capped exponential backoff with deterministic injectable jitter; default maximum 5 attempts. Also retry transient connection/timeouts and other 5xx, not permanent 4xx. Apply the limiter to every attempt. Include URL category/status/attempt in structured logs, but no response bodies or user-agent secrets.
12. Discover all 10-K/10-Q accessions from 2024-09-01 onward, not only `filings.recent`: follow every `filings.files[].name` submissions-history JSON file necessary to cover the cutoff. Preserve `acceptanceDateTime` from EDGAR and parse it as UTC into `accepted_ts`; do not substitute `filingDate`, `ingest_ts`, midnight, or the current time. If an archive row lacks acceptance time, fetch/parse authoritative filing metadata or log the filing `failed_missing_accepted_ts`; never publish a chunk with null/invented PIT time.
13. Before fetching filing bodies, obtain the distinct successful accession set already present in `bronze_sec_filings_v2` and anti-join candidates on normalized dashed `accession_number`. Also de-duplicate candidates within the run. Treat accession number as globally unique; if an existing accession is associated with a different CIK/ticker, log a conflict and fail that filing rather than appending duplicate ownership.
14. Add `${catalog}.${schema}.bronze_sec_ingest_log`, one append-only row per filing attempt: `run_id`, `ticker`, `cik`, `accession_number`, `form_type`, `filing_date`, `accepted_ts`, `status` (`planned|in_progress|succeeded|failed|skipped_existing|missing_cik`), `rows_appended`, `attempt`, `error_code`, redacted `error_message`, `started_ts`, `completed_ts`, and `dry_run`. Use a unique logical key `(run_id,ticker,accession_number,attempt)` when writing. On resume, accessions with a durable `succeeded` log and/or present bronze rows are skipped; `in_progress` or failed attempts are safe to retry because the final write performs a second accession anti-join.
15. Append each filing atomically as one batch after complete fetch/extraction/validation. Use a Delta `MERGE ... WHEN NOT MATCHED THEN INSERT` keyed by `record_key` for race safety, with an accession conflict check before the merge. Never `WHEN MATCHED UPDATE`, overwrite, or delete. Report actual inserted row count, not candidate count. A second identical run must append 0 bronze data rows.
16. `--dry-run` performs universe selection, cached/fixture CIK mapping, filing discovery, cutoff/form filtering and existing-accession anti-join, then prints/writes planned counts; it must not fetch filing bodies, append bronze data, run silver/embeddings, or mutate the persistent CIK cache. In dry-run, ingest-log persistence is off by default; `--log-dry-run` may append rows marked `dry_run=true`.
17. CLI flags must include `--catalog`, `--schema`, `--start-date` (default `2024-09-01`), `--forms` (default `10-K,10-Q` and reject other forms for this job), `--tickers`, `--include-historical`, `--dry-run`, `--log-dry-run`, `--refresh-cik-cache`, `--max-workers`, and `--run-id`. Bound filing workers (default 4); all workers share the limiter. Exit nonzero on configuration/table/schema failures, and emit totals for mapped/missing, discovered/existing/planned/succeeded/failed, requests/retries, and rows appended.

## 2. Silver sections and coverage

18. Update `silver/05_silver_sec_sections.sql:15-49` without changing its selection/chunk rules. Replace the unresolved `universe` relation with a CTE/view derived from `gold_tradable_universe`, and parameterize catalog/schema as supported by the existing pipeline. Process only source tickers/accessions absent from silver (source anti-join), while retaining the idempotent target MERGE. Do not limit to the original semiconductor names. Existing 10,720 rows must not change, and new tickers use the identical `record_key` IDs.
19. Only change `silver/06_silver_sec_entities.sql:18-128` as required to resolve the same universe relation; do not broaden forms/entity semantics as part of this task. Do not change `gold/gold_sec_features.py` feature logic; verify it accepts the expanded silver inputs without a hard-coded ticker list.
20. Add `gold/07_gold_sec_coverage.sql` creating or refreshing `${catalog}.${schema}.gold_sec_coverage` with exactly: `ticker STRING`, `cik STRING`, `n_filings BIGINT`, `n_chunks BIGINT`, `first_filed TIMESTAMP`, `last_filed TIMESTAMP`, `last_ingest_ts TIMESTAMP`. Build it from the intended universe left-joined to v2 filings/silver chunks so mapped tickers with zero chunks appear. `n_filings` is distinct chunk-bearing accessions; `first_filed`/`last_filed` are min/max `accepted_ts` (the names describe EDGAR filing acceptance, not `filing_date`); `last_ingest_ts` is max bronze `ingest_ts`. One row per canonical ticker, coalesce counts to zero, and use the latest successful ticker/CIK mapping where bronze has no filing.
21. Wire section MERGE, entities if currently part of refresh, and coverage refresh into the existing silver/gold runner in dependency order. Update `docs/DATA_SCHEMAS.md:124-140,316-329` for the ingest/mapping logs and coverage table, and update `docs/BRONZE_REFRESH_PLAN.md:690-700` to link the SEC runbook rather than leaving SEC ingestion only as a non-goal.

## 3. Incremental embeddings and manual Databricks job

22. Refactor `pipelines/build_sec_embeddings.py:25-145`. Keep idempotency on `(chunk_id, embedding_model)`, but do not `collect()` all existing IDs and all chunks (`:69-86`). Use a Spark left anti-join filtered to the configured embedding model, select only unembedded chunks, and stream/process bounded batches. Preserve `accepted_ts` via `unix_timestamp` as at `:79-82`. Add CLI flags `--catalog`, `--schema`, `--batch-size`, `--partitions`, `--ticker`, and `--limit`; `--ticker/--limit` support pilots. Validate vector dimension 384 and model `BAAI/bge-small-en-v1.5` before each append/MERGE.
23. Use `batch_size=256` per model call by default. Set CPU intra-op threads explicitly to avoid oversubscription and use 4 parallel embedding workers/partitions by default (`--partitions 4`, configurable 1-8). Each worker loads the model once; commits bounded result batches. If Spark worker model distribution is not reliable on serverless, use a bounded driver worker pool with at most 4 in-flight batches—never collect all texts/vectors at once.
24. Capacity plan: 350,000 chunks at roughly 2,000 characters each are about 175-250 million tokens. Budget 2-4 hours on one ordinary serverless CPU worker (roughly 25-50 chunks/s including tokenization/I/O) and 35-90 minutes with four effective CPU workers after model warm-up. This is a planning estimate, not an SLA: log measured chunks/s and ETA after the first 10,000 chunks, and abort/adjust parallelism if memory pressure or throttling occurs. With 384 float32 values, raw vectors are about 0.54 GB total; serialized/Delta overhead will be higher.
25. Add a separate `sec_embeddings` job in `resources/jobs.yml:1-30`, named `quant-platform-sec-embeddings-${bundle.target}`, with one `spark_python_task` pointing at `../pipelines/build_sec_embeddings.py`, parameters for `${var.catalog}` and `${var.schema}`, and the existing serverless environment pattern. Add a `catalog` bundle variable if necessary. It must have no `schedule` block and no trigger: manual only. Declare required packages in the serverless environment (including CPU torch/sentence-transformers dependencies already used by the repo) without embedding secrets in YAML.

## 4. Per-ticker lazy retrieval with a bounded, concurrent LRU

26. Replace the process-global all-corpus state in `api/services/hybrid_retriever.py:202-220` and `_load_corpus()` at `:237-386` with a `TickerCorpus` dataclass and one process-wide `OrderedDict[str,TickerCorpus]` LRU. `TickerCorpus` owns docs, tokenized docs/BM25 index, embedding matrix/map, stored model/dimension, load timestamp and approximate bytes. Parse `RAG_TICKER_CACHE_MAX` as a positive integer at startup, default 32; reject invalid/zero values. Never exceed this bound after a load completes.
27. Implement `_load_ticker_corpus(ticker)` with an uppercase canonical ticker required. Push `F.col("ticker") == ticker` into both Spark reads before `.collect()`; select chunks with `F.unix_timestamp(F.col("accepted_ts")).alias("accepted_epoch")` exactly as now (`:262-279`). Also filter embeddings by ticker and configured model. Do not load any other ticker. Join/match by chunk ID and retain chunks without embeddings for BM25-only fallback.
28. Preserve per-ticker checks now at `:281-309`: every stored vector has one dimension, it equals runtime embedding dimension, and stored model equals runtime model. A corrupt ticker fails independently and does not poison/clear other cached tickers. Keep model/dimension metadata inside `TickerCorpus`, not globals.
29. Thread safety: protect the LRU map/order with an `RLock`, and maintain a per-ticker in-flight load/future so concurrent first requests coalesce to one Spark load. Do not hold the global LRU lock during Spark I/O or embedding/scoring. Publish only fully built immutable corpus objects. On successful insertion, move the ticker to MRU and evict LRU entries until `len(cache) <= max`; an in-use local reference remains valid. On failed load, wake all waiters with the same exception and remove the in-flight marker so a later request can retry. `reload_corpus(ticker: str | None)` invalidates one ticker or all under lock without creating an eager reload.
30. Build one base BM25 index per ticker on load. PIT must still occur before scoring (`:427-446,470-486`): derive the eligible per-ticker docs first, then score only those documents. It is acceptable to create a temporary BM25 index for the PIT subset; never score the full index and filter afterward. Dense scoring must likewise slice/filter eligible embeddings before cosine similarity. Missing/null `accepted_ts` must be excluded (change the defensive inclusion at `:443-445`) because all newly published chunks require authoritative acceptance time.
31. Require one ticker. Keep `resolve_ticker_from_query` (`:127-199`) and extend its aliases from the coverage/mapping data if practical, but do not silently fan out across 300/557 tickers. `retrieve()` uses the explicit ticker, otherwise the resolver; if neither yields a ticker, raise a typed `TickerRequiredError` that the tool returns as `{"error":"ticker_required"}`. This bounds latency/memory and avoids ambiguous cross-company answers. Do not implement a default multi-ticker set.
32. Add a lightweight coverage lookup before loading/scoring. A ticker with no row or `n_chunks = 0` raises typed `NoCoverageError(ticker)`. In `agent/tools_retrieval.py:67-146`, catch it before broad fallback and return the exact single-element structure `[{"error":"no_coverage","ticker": symbol}]`; do not run substring fallback for this case. Preserve `retrieval_unavailable` for Spark/table/model/corpus failures and preserve the substring fallback only for genuine hybrid scoring failure where coverage/data are available.
33. Per-ticker budget for an expected average of ~630 chunks (350k/557): vectors are ~0.92 MB raw, text at ~2,000 characters is ~1.3 MB UTF-8, and Python `Document`, token, dict, NumPy, and BM25 overhead makes a realistic target 4-10 MB/ticker. Enforce/observe a soft 12 MB/ticker target and log `ticker`, chunks, embeddings, approximate bytes, load seconds, hit/miss and eviction without text. A 32-ticker cache should target <=384 MB corpus/index payload (excluding model/Spark runtime). Target warm cache retrieval p95 <250 ms excluding reranking/model query embedding; cold ticker load p95 <5 s under normal SQL connectivity. Tests assert the entry bound, not machine-specific timing.

## 5. Offline tests (all must fail on current code)

34. Add fixture files under `tests/rag/fixtures/sec/`: a minimal `company_tickers.json`, submissions recent + history payloads, one existing filing HTML used by the current corpus rules, 429/503 response scripts, and expected chunk IDs/text hashes. Fixtures contain no live secrets and tests make zero network/Databricks calls.
35. Add `tests/rag/test_sec_rag_ingest.py` covering:
    - exact, lowercase, whitespace, `BRK.B`/`BRK-B` class-share mapping; missing, ambiguous and delisted/override statuses are logged and never silently dropped;
    - fake-clock limiter proves every rolling 1-second window has <=10 starts, all concurrent workers share it, configured >10 is rejected, and 429/503 backoff honors `Retry-After`;
    - recent + archive discovery respects forms/cutoff;
    - fake store run 1 appends expected filing rows and run 2 appends 0; a simulated crash between `in_progress` and write resumes safely; accession ownership conflict fails;
    - `acceptanceDateTime` survives parse/write exactly (UTC epoch equality), and missing acceptance time cannot publish;
    - dry-run fetches no body and writes no data;
    - re-chunk the checked-in existing filing fixture and assert the complete ordered `(section, chunk_index, chunk_text hash, record_key)` golden list, proving parity and stable IDs.
36. Extend `tests/rag/test_hybrid_retriever.py` (current corpus/load and PIT tests) with fully fake Spark/table/row and fake embedding objects:
    - requesting ticker A only applies ticker filters to both table reads and never collects B;
    - cache max 2, access order A/B/A/C evicts B, length never exceeds 2, and reload-one/all semantics;
    - ticker A with past/future accepted epochs proves both BM25 and dense future chunks are excluded before score calls;
    - 20 concurrent first requests for A execute exactly one loader, return complete identical corpus, do not deadlock; concurrent A/B loads preserve bound;
    - per-ticker mixed dimension/model failure does not evict/corrupt a healthy cached ticker;
    - absent/zero coverage raises `NoCoverageError`; missing ticker raises `TickerRequiredError`.
37. Extend `tests/rag/test_edgar_adapter.py` or add `tests/rag/test_sec_retrieval_tool.py` to assert `search_sec_filings` returns exactly `[{"error":"no_coverage","ticker":"XYZ"}]` and does not invoke substring fallback; keep a separate `retrieval_unavailable` assertion.
38. Add `tests/rag/test_sec_embeddings_incremental.py` using fake dataframe/embedding/store adapters: only anti-joined chunk IDs are embedded, configured batches remain bounded, model/dimension are validated, and a second run writes zero. Add static YAML assertions that `sec_embeddings` exists and has no schedule/trigger.
39. Add `tests/rag/test_sec_coverage_sql.py` static/fixture contract checks: universe left join, one row per ticker, zero chunk count, distinct accession count, accepted timestamps rather than filing date, and max ingest timestamp.
40. Tests must explicitly hide optional runtime modules before imports (for example monkeypatch `sys.modules["pyspark"]` and `sys.modules["databricks.connect"]` to `None`) and must pass on Windows. Use `pathlib`, no shell-only assumptions. All new tests must fail against the pre-change commit for the intended missing behavior, not due to import/fixture errors.

## 6. Documentation and live runbook for Claude on WSL

41. Add `docs/SEC_RAG_COVERAGE_RUNBOOK.md` containing the following sequence with bundle target/catalog/schema variables and a timestamped `RUN_ID`. Never echo `SEC_EDGAR_USER_AGENT`; verify only that it is nonempty. Commands may be adjusted to the repo's Databricks profile, but the documented CLI contract must be exact.

### Dry run

```bash
export SEC_EDGAR_USER_AGENT='<set locally or inject from Databricks secret; never commit>'
databricks bundle validate -t dev
databricks bundle deploy -t dev
databricks bundle run -t dev sec_rag_ingest -- --dry-run --start-date 2024-09-01 --forms 10-K,10-Q
```

The build must add a manual `sec_rag_ingest` serverless job in `resources/jobs.yml` for this command, separate from the manual `sec_embeddings` job and with no schedule/trigger. Its task invokes `../pipelines/sec_rag_ingest.py`. Document the supported way to inject the User-Agent from a Databricks secret/task environment; do not put the value in bundle state or source.

### Ten-new-ticker pilot

Select pilot symbols dynamically so they are current-universe members with zero chunks; do not hard-code names that may already be covered:

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

Run the ingestion job with the comma-separated result, run the silver/coverage refresh, then run embeddings for the same tickers (one invocation per ticker or a documented comma-list if implemented):

```bash
databricks bundle run -t dev sec_rag_ingest -- --tickers "$PILOT_TICKERS" --start-date 2024-09-01 --forms 10-K,10-Q --run-id "$RUN_ID"
databricks bundle run -t dev silver_gold_refresh
databricks bundle run -t dev sec_embeddings -- --ticker "$PILOT_TICKERS" --batch-size 256 --partitions 4
```

### Verification SQL after pilot and full run

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

-- PIT sanity: accepted time is present, not backfilled from filing date, and silver preserves bronze.
SELECT count(*) AS null_accepted FROM ${catalog}.${schema}.silver_sec_sections WHERE accepted_ts IS NULL;
SELECT count(*) AS accepted_before_filing
FROM ${catalog}.${schema}.silver_sec_sections
WHERE accepted_ts < cast(filing_date AS timestamp);
SELECT count(*) AS pit_mismatch
FROM ${catalog}.${schema}.silver_sec_sections s
JOIN ${catalog}.${schema}.bronze_sec_filings_v2 b ON s.chunk_id=b.record_key
WHERE unix_timestamp(s.accepted_ts) <> unix_timestamp(b.accepted_ts);

-- Embedding completeness for chunk-bearing pilot tickers
SELECT s.ticker,count(*) chunks,count(e.chunk_id) embedded
FROM ${catalog}.${schema}.silver_sec_sections s
LEFT JOIN ${catalog}.${schema}.gold_sec_chunk_embeddings e
  ON s.chunk_id=e.chunk_id AND e.embedding_model='BAAI/bge-small-en-v1.5'
WHERE s.ticker IN (<quoted pilot tickers>) GROUP BY s.ticker;
```

Also execute `search_sec_filings(ticker, query, as_of)` for each pilot ticker with `as_of` after its latest acceptance and assert at least one result, then with `as_of` one second before its first acceptance and assert no future document is returned. Test a known zero-coverage ticker and assert `no_coverage`, not `retrieval_unavailable`.

After the pilot passes, run the default phase-1 job (current 300), refresh silver/coverage, and run the manual embedding job. Re-run all SQL and the retrieval smoke test. Then repeat ingestion with `--include-historical` for the remaining historical members and the same downstream sequence. A final identical ingestion rerun must report zero bronze rows appended; a final embedding rerun must report zero rows written. Record missing/ambiguous CIKs and failed filings for remediation rather than declaring them covered.

## 7. Acceptance commands

MiMo must run these offline on Windows with SEC network and Databricks unavailable:

```bash
python -m pytest tests/rag/test_sec_rag_ingest.py -q
python -m pytest tests/rag/test_hybrid_retriever.py tests/rag/test_sec_retrieval_tool.py -q
python -m pytest tests/rag/test_sec_embeddings_incremental.py tests/rag/test_sec_coverage_sql.py -q
python -m pytest tests/rag -q
python -m pytest -q
python -m ruff check pipelines/sec_rag_ingest.py pipelines/build_sec_embeddings.py api/services/hybrid_retriever.py agent/tools_retrieval.py tests/rag
python -m compileall pipelines api/services agent
git diff --check
```

If the repository uses a different established lint invocation, use it in addition to (or document why it replaces) the ruff command. No acceptance command may contact SEC or Databricks. MiMo must also inspect the staged diff to prove `.agents/dispatch.sh` was untouched.

## 8. DeepSeek must check

DeepSeek's verdict must be `APPROVED` or `CHANGES_REQUESTED` with file:line evidence and explicitly cover:

1. **Point-in-time `accepted_ts`:** sourced from EDGAR acceptance datetime (including history files), parsed/preserved through bronze, silver, embeddings and retrieval; null/invented values cannot publish; PIT filtering occurs before both BM25 and dense scoring.
2. **Idempotency/resume:** accession anti-join happens before body fetch and again atomically at write; second run appends zero; races/crashes do not duplicate; no matched updates/deletes violate append-only semantics.
3. **Chunk parity:** one shared extraction implementation preserves all current patterns/caps/size/overlap/key inputs; golden existing filing reproduces identical ordered text and `record_key`/silver `chunk_id`.
4. **LRU memory bound/concurrency:** ticker predicates are pushed to both reads, cache never exceeds `RAG_TICKER_CACHE_MAX`, in-flight loads coalesce safely, eviction does not corrupt active requests, failures are isolated per ticker, and no all-corpus fallback remains.
5. **Rate limiting/fair access:** every request and retry uses one shared limiter, rolling rate never exceeds 10 req/s, configured default is 8, required User-Agent is external, and 429/503 backoff/Retry-After are honored.
6. CIK class-share/missing/ambiguous/delisted behavior is explicit and auditable; no ticker is silently dropped.
7. The embedding builder does a distributed/source anti-join and bounded batches rather than driver-wide collects; job is serverless and manual only.
8. `no_coverage`, `ticker_required`, and `retrieval_unavailable` remain distinct and broad exception fallback cannot mask the first two.
9. All offline tests genuinely hide `pyspark`/`databricks.connect`, use no network, and each requested regression would fail on the pre-change code for the correct reason.

## 9. Delivery constraints

- LF line endings everywhere.
- Do not touch `.agents/dispatch.sh`.
- Do not commit secrets, a real SEC contact string, live payloads containing sensitive data, or Databricks credentials.
- MiMo must implement, run the offline acceptance suite, commit all intended changes, and write `.agents/mimo/VERDICT-rag-coverage.md` with commit SHA, changed files, commands/results, known limitations, and a concise live-run handoff.
- Do not perform the live SEC/Databricks run from MiMo's Windows environment.
- After MiMo's commit, DeepSeek must review and write `.agents/deepseek/VERDICT-rag-coverage.md`; Codex validation starts only after that verdict says APPROVED.
