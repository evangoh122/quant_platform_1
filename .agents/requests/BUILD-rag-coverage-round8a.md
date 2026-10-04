# BUILD rag-coverage round 8a — ingest correctness (builder: MiMo; checker: DeepSeek; reviewer: Codex)

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/rag-coverage. Commit after EACH item with a descriptive message.
NEVER delete or weaken existing tests. Codex review: .agents/codex/VERDICT-rag-coverage-review.md (10×P1). This round = findings 1–6
(pipelines/sec_rag_ingest.py, api/services/xbrl_client.py). Round 8b will do 7–10 — do NOT touch build_sec_embeddings.py, hybrid_retriever.py,
gold/07, tools_retrieval.py in this round. Each fix needs a test that FAILS on the old code (run it in a /tmp copy and paste the output).

1. Atomic, typed bronze writes (:1256-1257): explicit StructType (raw_payload typed even when null); replace the plain append with a Delta MERGE
   keyed on accession_number (insert-only when not matched; ownership conflict = same accession with a different cik → AccessionOwnershipConflict),
   so concurrent/re-runs can't duplicate; report the actual inserted count (from MERGE metrics / operationMetrics, or a pre/post count of the
   batch's keys). Fake-Spark tests: explicit schema; MERGE (not append) issued; re-run → 0 inserted.
2. accepted_ts UTC (:210): never hand Spark a naive datetime. Pass tz-aware UTC datetimes or epoch → `to_timestamp`/`timestamp_seconds` in Spark.
   Test under TZ=Asia/Singapore + time.tzset(): 2025-02-20T18:30:00Z → epoch 1740076200 in what's written (not 1740047400).
3. Discovery must not silently succeed on incomplete data (:606): exhausted submissions retries → raise / record `failed` for that ticker in
   sec_ingest_log (never "0 filings, success"); history-file failures recorded too. History inclusion = the file OVERLAPS [start_date, now]
   (use filingFrom/filingTo), not `filingFrom < start_date`. `_collect_filings` must not truncate to the acceptance array length — a row with a
   missing acceptanceDateTime is recorded as skipped/invalid with a reason, not silently dropped. Tests for each.
4. CIK mapping: duplicate ticker → different CIKs = `ambiguous` (do not pick the last); add `ambiguous` back to the emitted statuses AND to
   docs/DATA_SCHEMAS.md (the ontology PR #22 will be updated to match — note it in your verdict). Stale-cache fallback (:840): on network failure,
   use the cached sidecar regardless of age (log its age), raise only if no cache; `_try_load_cache(ttl=0)` bug fixed. Dry runs must NOT write
   the persistent cache. Tests: two-CIK fixture → ambiguous; network failure + 30-day-old cache → uses cache; dry run → cache file unchanged.
5. SEC fair access: ONE process-wide limiter (module-level singleton, thread-safe) shared by sec_rag_ingest and xbrl_client, ≤ 10 req/s
   aggregate. Parse Retry-After as seconds OR HTTP-date (email.utils.parsedate_to_datetime). Tests: two clients in parallel threads → aggregate
   ≤ 10 in any 1-s window; HTTP-date Retry-After honoured.
6. Resume + workers: `max_workers` actually used (bounded ThreadPoolExecutor over filings, sharing the global limiter); persist `in_progress`
   before work; attempt = previous attempts + 1 (read sec_ingest_log for the run/ticker/accession); resume skips succeeded accessions from the
   log; ownership conflict records the filing as failed (with reason) THEN raises/continues per policy (state which). Tests for each.
Acceptance: python3 -m pytest tests/rag tests/bronze -q all pass; pyspark hidden (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps).
.agents/mimo/VERDICT-rag-coverage-round8a.md with counts + every mutation output. Commit everything.
