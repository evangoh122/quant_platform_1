===VERDICT START===
# VERDICT: rag-databricks — DeepSeek (independent checker)
**Status:** CHANGES_REQUESTED
**Round:** check (post-MiMo round 5)

## Blocking findings

- [agent/tools_retrieval.py:140] `as_of.strftime("%Y-%m-%d %H:%M:%S")` drops
  `tzinfo`, then `F.lit(as_of_str).cast("timestamp")` interprets the string in
  the **Spark session timezone**. `accepted_ts` is a native `TIMESTAMP`
  (silver/05_silver_sec_sections.sql:22, docs/DATA_SCHEMAS.md:322), i.e. an
  instant. Concrete failure: `as_of = datetime(2025,6,1,0,0,0, tzinfo=timezone(timedelta(hours=8)))`
  → `strftime` yields `"2025-06-01 00:00:00"`; cast in a UTC session this becomes
  `2025-06-01T00:00Z`, but the true instant is `2025-05-31T16:00Z` (verified:
  probe printed `2025-05-31 16:00:00` for the UTC equivalent). Filings accepted
  in that 8-hour window leak through the point-in-time filter. Same bug fires
  when `as_of` is UTC-aware but the session timezone is not UTC.

- [api/services/hybrid_retriever.py:373,468] A **naive** `as_of` makes the
  comparisons `accepted_dt <= as_of` / `accepted_dt > as_of` raise
  `TypeError: can't compare offset-naive and offset-aware datetimes`
  (`_parse_ts` always returns an aware UTC datetime — verified by probe). That
  `TypeError` is swallowed by the generic `except Exception` at
  agent/tools_retrieval.py:128, silently abandoning the whole hybrid path
  (BM25 + dense + RRF + cross-encoder) and dropping into the substring
  fallback. Concrete input: `search_sec_filings("NVDA", query="revenue", as_of=datetime(2025,6,1))`
  → hybrid raises → results come back tagged `substring_fallback`, losing
  semantic retrieval and reranking on a call that should have succeeded. The
  fallback then re-enters the tz-unsafe `strftime` path above.

- [tests/rag/test_hybrid_retriever.py] The point-in-time filter is tested only
  in isolation (`TestPITFilter` calls `_pit_filter` directly), never through
  `bm25_search` / `vector_search` / `retrieve`. Mutation proof: in a `/tmp` copy
  I removed the PIT filter from **both** `bm25_search` (`docs = _bm25_docs`) and
  `vector_search` (deleted the `as_of` block) — the full suite still reported
  **248 passed, 19 skipped**. A removed PIT filter in the production retrieval
  path is therefore not caught by any test. (By contrast, inverting the RRF
  formula `1/(k+rank+1)` → `rank+1` fails `test_basic_fusion_merges_rankings`
  and `test_single_ranking_list`, so RRF is at least smoke-guarded.)

## Non-blocking notes

- [api/services/hybrid_retriever.py:277,341] `_load_corpus` stores
  `str(row["accepted_ts"])`. A Spark `TIMESTAMP` collected off a non-UTC
  session yields a naive session-local `datetime`; `str()` drops the offset and
  `_parse_ts` then assumes UTC, shifting every hybrid-path cutoff by the
  session offset. Same root cause as the fallback finding; harmless only when
  the session is UTC.
- [api/services/hybrid_retriever.py:466] `vector_search` does not default
  `as_of=None` to `now(UTC)` (unlike `_pit_filter`, which does). So
  `HybridRetriever().retrieve(q)` with no `as_of` filters BM25 by `now` but
  leaves dense unfiltered — inconsistent PIT defaults between the two lanes.
  (Not hit via `search_sec_filings`, which always sets `as_of`.)
- [pipelines/build_sec_embeddings.py:74,128] f-string SQL
  (`filter(f"embedding_model = '{EMBEDDING_MODEL}'")`, `MERGE`, `CREATE TABLE`).
  These interpolate env/config constants, not user input, so they are not an
  injection vector — but they violate the "parameterized queries only" mandate.
- [api/services/reranker.py:66] If the cross-encoder fails to load, `rerank`
  silently returns the un-reranked list. Graceful and non-leaking, but the
  "rerank to top 5" guarantee is dropped without any tag/flag.
- [api/services/hybrid_retriever.py:348] `_parse_ts` contains a no-op
  `if "+" not in ts_str and ts_str.endswith(":00"): pass` branch (dead code).

## Fidelity check (spec vs code)

- bge-small-en-v1.5, 384-d — OK (embeddings.py:23-24).
- BM25Okapi — OK (hybrid_retriever.py:34,303,409).
- top_k×2 candidates per retriever — OK (hybrid_retriever.py:541,548).
- RRF k=60 — OK (hybrid_retriever.py:78, 511; `1/(k+rank+1)` with 0-based rank).
- cross-encoder ms-marco-MiniLM-L-6-v2, top 5 — OK (reranker.py:24,55; default `top_k=5`).
- PIT before scoring — OK in structure (bm25: filter then rebuild index, line 402;
  dense: filter inside loop, line 466-469) but subject to the tz/naive defects above.

## Checks run

- `python3 -m pytest tests/rag -q` → **248 passed, 19 skipped** (repo HEAD).
- Mutation: remove PIT from `bm25_search` + `vector_search` (/tmp copy) →
  `pytest tests/rag -q` → **248 passed** (defect NOT caught).
- Mutation: invert RRF formula (/tmp copy) → `pytest tests/rag/test_hybrid_retriever.py -q`
  → **2 failed** (defect caught).
- Probe `_pit_filter` with naive `as_of` → `TypeError: can't compare offset-naive
  and offset-aware datetimes`.
- Probe `as_of.strftime` on tz-aware +08:00 → `"2025-06-01 00:00:00"` vs correct
  UTC equivalent `"2025-05-31 16:00:00"`.
===VERDICT END===
