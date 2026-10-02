===VERDICT START===
# VERDICT: rag-databricks — DeepSeek (independent checker, re-check)
**Status:** APPROVED
**Round:** check2 (post rounds 6-7, HEAD bd0097a)

## Blocking findings

None. All three findings from the round-5 check are resolved at HEAD, and the
round-7 client-timezone fix is correct under the standard Databricks serverless
configuration (session timezone = UTC), which Claude's live smoke confirms.

## Re-verification of the three earlier blocking findings

1. **Fallback `strftime` tz leak → RESOLVED.** `agent/tools_retrieval.py:140-144`
   now compares epoch seconds: `int(as_of.timestamp())` vs
   `F.unix_timestamp(F.col("accepted_ts"))`. `as_of` is normalized to UTC-aware
   by `_normalize_as_of` (tools_retrieval.py:86), so `as_of.timestamp()` is the
   correct UTC epoch regardless of the caller's tz. Probe: `as_of = 2025-06-01
   00:00 +08:00` → normalized `2025-05-31 16:00Z`; a filing at `2025-05-31
   20:00Z` is correctly excluded (`_pit_filter` returned 0 docs).

2. **Naive `as_of` → TypeError → silent fallback → RESOLVED.**
   `_normalize_as_of` (hybrid_retriever.py:39-52) tags naive datetimes as UTC,
   and `_pit_filter` / `bm25_search` / `vector_search` / `retrieve` all call it
   before any comparison. `_parse_ts` returns an aware UTC datetime, so the
   comparisons are aware-vs-aware. Probe: `_pit_filter([doc], as_of=datetime(2025,6,1))`
   returns the doc with no `TypeError`; `search_sec_filings` no longer drops to
   the substring fallback for a naive `as_of` (covered by
   `TestSearchSecFilingsError::test_naive_as_of_returns_hybrid_mode`).

3. **PIT filter untested through the retrieval path → RESOLVED.**
   `TestPITIntegrationRetrieval` exercises `bm25_search`, `vector_search`, and
   `retrieve` with a future-dated chunk; `TestPITMutationProof` additionally
   proves the filter is load-bearing. Mutation proof at HEAD: deleting the PIT
   filter from both `bm25_search` (`docs = _pit_filter(...)` → `docs = _bm25_docs`)
   and `vector_search` (removed the `accepted_dt > as_of` block) in a `/tmp`
   copy produced **5 failed** tests (`test_bm25_excludes_future_chunk`,
   `test_vector_excludes_future_chunk`, `test_retrieve_excludes_future_chunk`,
   `test_mutation_remove_pit_from_bm25_fails`, `test_mutation_remove_pit_from_vector_fails`).
   Inverting the RRF formula (`1.0/(k+rank+1)` → `float(k+rank+1)`) still fails
   `test_basic_fusion_merges_rankings` and `test_single_ranking_list` (**2 failed**).

## Round-7 client-timezone fix

- `_load_corpus` (hybrid_retriever.py:266-273, 298-304) and `build_sec_embeddings`
  (build_sec_embeddings.py:84-87, 116-120) now `SELECT unix_timestamp(accepted_ts)`
  and convert in Python via `datetime.fromtimestamp(int(epoch), tz=timezone.utc)`.
- This is the correct fix for the round-6 bug: `collect()` of a Spark TIMESTAMP
  materializes a naive datetime in the *client's* local timezone, whereas the
  epoch (a `BIGINT`) is timezone-invariant on the wire.
- `accepted_ts` is a native Spark `TIMESTAMP` (silver/05_silver_sec_sections.sql:23,
  docs/DATA_SCHEMAS.md:322), stored as naive UTC wall-clock by ingestion
  (notebooks/02_ingest_sec_edgar.py:261-267 strips tzinfo from the UTC-parsed
  EDGAR timestamp). `unix_timestamp` interprets that wall-clock in the *session*
  timezone, so the fix is exactly correct iff session timezone = UTC — the
  Databricks serverless default, and consistent with Claude's live smoke
  (`as_of=2025-01-01 +08:00` and naive `2025-01-01` both → `retrieval_mode=hybrid`,
  only the 2024-11-20T21:31Z NVDA filing). See the non-blocking note below.

## Non-blocking notes

- [api/services/hybrid_retriever.py:266-273, pipelines/build_sec_embeddings.py:84-87]
  The epoch read assumes the Spark **session** timezone is UTC (`accepted_ts` is
  stored as naive UTC wall-clock, and `unix_timestamp` applies the session tz).
  It holds on Databricks serverless today, but it is an implicit contract. Make it
  explicit — set `spark.sql.session.timeZone = 'UTC'` in `_get_spark()`, or read
  `to_utc_timestamp(accepted_ts, <session-tz>)` — so a future non-UTC cluster
  config cannot silently shift the PIT cutoff by the offset.
- [pipelines/build_sec_embeddings.py:73-75,139-145] f-string SQL (`filter(f"embedding_model
  = '{EMBEDDING_MODEL}'")`, `CREATE TABLE`/`MERGE` over `EMBEDDINGS_TABLE`). Still
  env/config constants, not user input, so no injection vector — but it remains a
  "parameterized-only" mandate violation (prefer `F.col(...) == F.lit(...)`).
- [api/services/reranker.py:66-68] If the cross-encoder fails to load, `rerank`
  silently returns the un-reranked list; the "rerank to top 5" guarantee is
  dropped with no tag. Graceful, non-leaking, but untracked.
- [api/services/hybrid_retriever.py:375-376] Dead `if "+" not in ts_str and
  ts_str.endswith(":00"): pass` branch in `_parse_ts`.
- [agent/tools_retrieval.py:162] The substring fallback returns `accepted_ts` via
  `r.get("accepted_ts", "")` from the raw collected row (a naive session-local
  datetime), not a UTC ISO string like the hybrid path. Cosmetic display drift in
  the degraded path only; the fallback's PIT *filter* (line 143) is epoch-based
  and correct.

## Checks run

- `python3 -m pytest tests/rag -q` → **264 passed, 19 skipped** (HEAD).
- Mutation: remove PIT filter from `bm25_search` + `vector_search` (/tmp copy) →
  `python3 -m pytest tests/rag -q` → **5 failed** (defect caught).
- Mutation: invert RRF formula (/tmp copy) → `python3 -m pytest tests/rag/test_hybrid_retriever.py -q`
  → **2 failed** (defect caught).
- Probe `_pit_filter` with naive `as_of=datetime(2025,6,1)` → no `TypeError`,
  returns the doc; `_normalize_as_of` yields `2025-06-01T00:00:00+00:00`.
- Probe `_normalize_as_of(datetime(2025,6,1,0,0,0,tzinfo=+08:00))` →
  `2025-05-31T16:00:00+00:00`; filing `2025-05-31T20:00:00+00:00` excluded.
===VERDICT END===
