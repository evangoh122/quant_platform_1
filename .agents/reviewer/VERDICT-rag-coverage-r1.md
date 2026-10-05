===VERDICT START===
Reviewer: Claude Sonnet subagent (stopgap for Codex, usage-limited)
Status: CHANGES_REQUESTED

Tests: `python3 -m pytest tests/rag tests/bronze -q` = 629 passed, 36 skipped, 0 failed.

## Codex's 10 findings, re-verified
1 bronze MERGE: FIXED for a single writer (typed StructType, MERGE keyed on accession, count from DESCRIBE HISTORY). NEW defect, see N1.
2 accepted_ts UTC: FIXED. Probe under TZ=Asia/Singapore gave epoch 1740076200 (correct).
3 discovery: PARTIALLY FIXED. Top-level failure is logged as discovery_failed. Missing acceptanceDateTime is kept. History overlap is fixed. History-file fetch failure is still swallowed, see N2.
4 CIK: FIXED. Two CIKs for one ticker give "ambiguous". A 115-day-old cache is used after a fetch failure. A dry run does not write the cache.
5 limiter: FIXED. xbrl_client.get_global_limiter is the same object as the ingest one. HTTP-date Retry-After is parsed. Caveat N3.
6 workers/resume: FIXED. ThreadPool uses max_workers, in_progress is persisted, attempt = prev+1, SparkIngestLogReader is wired in main. Resume relies on the accession anti-join.
7 embeddings: FIXED. Unique view per batch, merge_lock, comma ticker isin. Caveats N4 and N5.
8 retrieval: FIXED. reload_corpus(None) no longer loads eagerly. Dense search excludes NULL or unparseable accepted_ts (hybrid_retriever.py:873).
9 coverage SQL: FIXED. Placeholders, universe CTE and the latest-mapped-log CIK are in place. run_silver_gold.py:147 substitutes {catalog}/{schema}.
10 table errors: FIXED. get_coverage rethrows, and tools_retrieval.py:153 returns retrieval_unavailable.

## New findings
N1 [P1] Bronze MERGE races under the default `--max-workers 4`. sec_rag_ingest.py:1553 uses the fixed view name `_merge_src` on one shared Spark session, with no lock. This is the same defect Codex raised as finding 7 for embeddings, left unfixed here.
- Worker A can MERGE worker B's rows.
- A then logs "succeeded" with A's accession never inserted. Resume skips it only if it landed; otherwise it is retried.
- The `DESCRIBE HISTORY LIMIT 1` read at ~1600 is also unlocked, so rows_appended can come from another worker's MERGE.
- Concurrent Delta MERGEs on one table will raise conflicts (ConcurrentAppend), which are logged as "failed".
- Fix: uuid view name, a serialising lock around MERGE plus history read, and a test with concurrent calls.
N2 [P2] Failed history-file fetches (sec_rag_ingest.py ~714) only log a warning and `continue`. At 557 symbols 429 exhaustion is likely, so the run reports partial coverage as success. The ticker should be marked discovery_failed.
N3 [P2] A 429 only sleeps the calling worker. The other workers keep hitting SEC, with no shared cool-down. Retry-After is not clamped: a probe returned 2.3e9 s for a far-future date. Add a global pause and cap it (about 300 s).
N4 [P2] build_sec_embeddings.py:~293 `return inserted if inserted > 0 else len(out_rows)` reports candidate rows when 0 were inserted.
N5 [P2, needs a live check] Neither job sets sys.path, yet both import `pipelines.*` and `api.*`. The embeddings environment lacks loguru and python-dotenv (imported by api/config.py). Verify with a one-ticker live run on Databricks.
N6 [P3] SparkIngestLogReader issues one Spark query per filing, which is thousands of round trips at scale. Filings with a missing accepted_ts are marked failed and re-fail on every run.

## Mutations (copies under /tmp, all killed)
M1 naive-UTC timestamp (TZ=Asia/Singapore): TestParseSecTimestamp::test_iso_format failed.
M2 fixed embeddings view name: test_concurrent_batches_use_distinct_view_names failed.
M3 HTTP-date Retry-After dropped: TestFairAccess::test_http_date_retry_after failed.
Score: 3/3 killed.

Scale (557 symbols): the corpus is loaded per ticker via LRU, so memory is OK. N1 and N3 are the main risks for an unattended run. Until N1 is fixed, a workaround is `--max-workers 1`.
===VERDICT END===
