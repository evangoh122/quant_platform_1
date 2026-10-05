===VERDICT START===
# VERDICT: rag-coverage — DeepSeek (schema/API contract reviewer)
**Status:** CHANGES_REQUESTED
**Round:** 1 (HEAD 2925332)

## Blocking findings

1. **[api/services/hybrid_retriever.py:415, :1006-1080; agent/tools_retrieval.py:95-100]
   Coverage lookup and error contract are never wired into the live path.**
   `check_ticker_coverage()` is defined but never called by `HybridRetriever.retrieve()`
   or `search_sec_filings()`. `TickerRequiredError` is never raised anywhere in
   production code — `resolve_ticker_from_query` returns `""` and `retrieve()`
   silently proceeds. `NoCoverageError` is only raised from the (uncalled)
   coverage helper. → A ticker with `n_chunks=0` flows `get_ticker_corpus` →
   `_load_ticker_corpus` (empty) → `bm25_search`/`vector_search` return `[]` →
   `search_sec_filings` returns **`[]`**, not the required
   `[{"error":"no_coverage","ticker":symbol}]`. `test_sec_retrieval_tool.py:26-55`
   mocks `HybridRetriever` to raise these errors directly, so it proves only the
   except-branch handling, never that the real path raises them. CHECK items 4 & 5
   fail.

2. **[api/services/hybrid_retriever.py:336-372, :449-587, :819-833, :919-982]
   The all-corpus fallback remains.** `get_ticker_corpus` has a global-corpus
   fallback branch; `bm25_search`/`vector_search` with an empty ticker still call
   `_load_corpus()` which does a full-corpus `collect()`. Spec §4.26/§4.31 require
   removing this and raising `TickerRequiredError` instead of silently fanning out
   across all tickers. → An empty-ticker query loads every ticker's corpus in the
   driver, defeating the per-ticker LRU bound. CHECK item 4 ("NO all-corpus
   fallback") fails.

3. **[silver/05_silver_sec_sections.sql:44; silver/06_silver_sec_entities.sql:44,66,98,145;
   pipelines/run_silver_gold.py:84-88] Silver is still gated by the MVP universe,**
   not `gold_tradable_universe`. Both transforms filter `ticker IN (SELECT symbol
   FROM universe)`, and `register_universe()` reads `config/universe.yaml` (~45
   symbols, ~16 with SEC coverage). Spec §1.18 requires "replace the `universe`
   relation with a CTE/view derived from `gold_tradable_universe`" and "do not
   limit to the original semiconductor names". → The 300/557 new tickers ingested
   into `bronze_sec_filings_v2` will never reach `silver_sec_sections`, so
   embeddings and retrieval remain semiconductor-only. This is the core of the
   feature and it is not delivered.

4. **[silver/05_silver_sec_sections.sql:28-30] `chunk_index` ordering changed.**
   `ROW_NUMBER() ... ORDER BY chunk_id` → `ORDER BY src.record_key` (a sha256
   hash). Spec §1.18 requires "without changing its selection/chunk rules". → For
   new tickers, `chunk_index` becomes the hash order, not `chunk_id - 1`, so the
   0-based ordinal is scrambled (the bronze integer `chunk_id` is the ordinal, per
   spec §1.3). The anti-join protects the existing 10,720 rows but silently
   corrupts every new row's `chunk_index`.

5. **[pipelines/build_sec_embeddings.py:113, :64, :129-156] Anti-join still
   `collect()`s everything to the driver; `partitions` is dead.** The left_anti
   join is correct, but `new_rows = anti_join_df.collect()` pulls all unembedded
   chunk text + metadata into driver memory, and embedding runs sequentially in a
   for-loop. `partitions` is accepted but never referenced (no `repartition`, no
   worker pool). Spec §1.22-23 forbid "collect all texts/vectors at once" and
   require "4 parallel embedding workers/partitions". → ~350k chunks would blow
   the driver memory budget. CHECK item 7 fails.

6. **[tests/rag/ — absent] Per-ticker LRU concurrency/eviction tests were not
   written (spec §5.36).** No test exercises the LRU cache bound/eviction, in-flight
   load coalescing, per-ticker isolation, per-ticker dim/model validation, or
   `NoCoverageError`/`TickerRequiredError` raised through `retrieve()`. The MiMo
   verdict claims "87 tests preserved + 2 modified", but none of the §5.36 tests
   exist. CHECK items 4 & 6 ("prove" the LRU behaviours) fail.

7. **[pipelines/sec_rag_ingest.py:113-120, :999-1003, :1050-1058] Accession
   ownership conflict is not implemented.** `ExistingAccessionReader` returns a
   bare `Set[str]` of accessions with no CIK/ticker, so "an existing accession
   associated with a different CIK/ticker" (spec §1.13) cannot be detected. The
   test `test_accession_ownership_conflict_fails` (test_sec_rag_ingest.py:845)
   only asserts skip-existing, not conflict.

8. **[notebooks/02_ingest_sec_edgar.py:55,382,1620,1025,3063,3191,3490;
   etl/extract_edgar.py:33-39] The notebook/ETL refactor was not done.** The
   notebook still hard-codes `UNIVERSE_STK` and `max_filings_per_ticker=8`, and
   keeps its own `build_cik_map`/parsing (a second production definition, violating
   spec §1.2 "exactly one production definition"). `etl/extract_edgar.py` still
   falls back to the placeholder `research@example.com` User-Agent (spec §1.9).

9. **[docs/DATA_SCHEMAS.md; docs/BRONZE_REFRESH_PLAN.md] Not updated (spec §1.21).**
   Only `docs/SEC_RAG_COVERAGE_RUNBOOK.md` was added; the ingest/mapping log and
   coverage-table schemas were not documented.

## Non-blocking notes

- [tests/rag/test_sec_rag_ingest.py:708-736] The "golden parity" test re-chunks the
  fixture and re-derives the key from the same inputs, then asserts the key equals
  itself — it does not assert a pre-computed golden `(section, chunk_index,
  text-hash, record_key)` list, so parity against the original notebook output is
  not actually proven (spec §5.35).
- [pipelines/sec_rag_ingest.py:900,1034] `max_workers` is accepted but unused; the
  filing loop is sequential (correct but under-parallel vs spec §1.17).
- [pipelines/sec_rag_ingest.py:508-517] `_parse_retry_after` handles numeric
  seconds only, not HTTP-date (spec §1.11 says "numeric or HTTP-date").
- [pipelines/sec_rag_ingest.py:634-637] `_collect_filings` truncates to
  `min(len(form),...,len(acceptance))`; an archive history file with an empty
  `acceptanceDateTime` array is silently skipped instead of logged
  `failed_missing_accepted_ts`.
- [pipelines/sec_rag_ingest.py:697-704] Dead `index_url` assignment in
  `fetch_filing_text`.
- [pipelines/build_sec_embeddings.py:120,186] `rows_already_embedded` now returns
  `-1`, losing the already-embedded count (acceptable under anti-join, but a
  regression in observability).
- [tests/rag/test_sec_embeddings_incremental.py:13-18] Uses
  `sys.modules.setdefault("pyspark", mock)`; this is a no-op if a harness already
  stubs `pyspark` to `None` (the spec §5.40 "to None" mechanism), so the module
  import fails under the stricter hide (5 failures reproduced below). Prefer the
  `fake_pyspark` fixture (`monkeypatch.setitem`) or plain assignment.
- [.agents/dispatch.sh] Uncommitted working-tree mode change (100755→100644),
  likely a WSL mount artifact. Not part of MiMo's commits (the commit range does
  not touch it), but re-add the executable bit before any PR.

## Checks run

- `python3 -m pytest -q -p no:cacheprovider tests/rag` → **383 passed, 19 skipped,
  7.65s** (hang fixed). PASS.
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase` → **656 passed,
  6 failed, 67 skipped, 115s**. The 6 failures are all in
  `tests/bronze/test_refresh_bronze_cot.py` (pre-existing, unrelated to this
  change — real `databricks.connect` mock `.columns` returns a MagicMock). FAIL
  (pre-existing).
- `PYTHONPATH=/tmp/hidemods python3 -m pytest -q -p no:cacheprovider tests/rag`
  (pyspark/databricks.connect stubbed to `None`) → **378 passed, 5 failed, 19
  skipped**. The 5 failures are `tests/rag/test_sec_embeddings_incremental.py` due
  to the `setdefault` fragility above. FAIL (reveals the §5.40 hiding gap).
- `git diff --check ff546bc..HEAD` → clean. PASS.
- `python3 -m compileall pipelines api/services agent` → clean. PASS.
- `python3 -m ruff check ...` → not runnable (ruff not installed in this WSL env).
- `git diff ff546bc..HEAD --stat -- tests/` → +1438 / −68 across 10 files; no large
  test deletions; `test_hybrid_retriever.py` retains 87 test functions.
- `git grep` of `check_ticker_coverage`/`TickerRequiredError` → no production
  caller of either (finding 1).

## Conclusion

The ingestion pipeline, rate limiter, CIK mapping, idempotency, and the
fail-closed `accepted_ts` PIT exclusion are solid and well-tested. But the
feature's central promise — RAG coverage beyond the 16 tickers — is not delivered
end-to-end: the silver transforms still gate on the MVP universe (finding 3), and
the retrieval path still has an all-corpus fallback and never raises
`no_coverage`/`ticker_required` (findings 1-2). These plus the missing §5.36 tests
(6) and the driver-wide `collect()` in the embedding builder (5) require another
round before Codex validation.
===VERDICT END===
