# VERDICT: RAG coverage round 4

Checker: Claude Sonnet subagent (DeepSeek out of credit)

Verdict: **CHANGES_REQUESTED**

Items 1, 2, 6 (columns) and 7 are met. Items 3, 4, 5 are not proven by tests, and
parts of 4 and 6 are incomplete. Mutation proofs below.

## Test runs (HEAD 55e7bcc)
- Normal: `python3 -m pytest tests/rag -q` -> 405 passed, 19 skipped.
- pyspark hidden (`PYTHONPATH=.../scratchpad/nps`): 405 passed, 19 skipped.
- pandas 3 venv (`.../scratchpad/p3/bin/python`): INCONCLUSIVE. The venv has no pip and lacks
  dotenv/duckdb/polars/pydantic/langchain_core/bs4: 6 collection errors on the full dir, 15
  failures on the two ingest/embedding files, all `ModuleNotFoundError` or MagicMock-from-missing-bs4.
  Not attributable to the branch.
- `tests/bronze/test_refresh_bronze_cot.py` was not run; the file is not touched by round 4
  (`git diff --stat 7813cd4..HEAD` shows no bronze files), so it is pre-existing as far as this branch is concerned.

## Test deletion/weakening (git diff 7813cd4..HEAD -- tests)
No assertions deleted. Removed lines are: the module-level `sys.modules.setdefault` pyspark
mocks (replaced by the `fake_pyspark` fixture, which is what item 7 asked for), the weakened
coalescing/isolation bodies from 4647b89 (restored: `test_hybrid_retriever.py` two-thread test with a
sleeping spy; isolation test now calls `get_ticker_corpus`, uses `pytest.raises((RuntimeError, CorpusUnavailableError))`,
a slight loosening but still asserts BBB loads and call_log == ["AAA","BBB"]).

## Findings

1. Coalescing (PASS, with one weak test).
   - `api/services/hybrid_retriever.py` ~335-372: lock only guards Future lookup/creation; load runs outside; `finally` pops inflight.
   - Mutation (old 7813cd4 `hybrid_retriever.py` in /tmp/ragcov-mut-1): `test_two_threads_one_load` and
     `test_four_threads_one_ticker_one_load` FAIL (good).
   - BUT `test_three_tickers_parallel` PASSES on the old serial code. Threshold `< 0.8s`
     with 3 x 0.2s = 0.6s serial cannot discriminate (tests/rag/test_hybrid_retriever.py ~2840). Tighten
     (e.g. 5 tickers x 0.3s, assert < 0.8s) or assert concurrent overlap with a barrier/max-concurrency spy.
2. Embedding parallelism (PASS). `pipelines/build_sec_embeddings.py` ThreadPoolExecutor, bounded by
   `max_workers=partitions`. Mutation (old file): `test_concurrent_embedding_workers` FAILS (good).
   Nit: comment claims each worker initialises its own model, but `get_embeddings()` is a singleton
   (`api/services/embeddings.py:154`), so the model is shared across threads; fine if thread-safe, but fix the comment.
3. main() wiring (FAIL: not proven). `pipelines/sec_rag_ingest.py:1270-1293` does pass adapters, and
   `SparkUniverseReader` defaults to gold_tradable_universe with `--include-historical`. However
   mutation (remove the four adapter kwargs from the `run_ingest` call, /tmp/ragcov-mut-3): all 66 tests in
   `test_sec_rag_ingest.py` still PASS. `TestMainEndToEnd` dry-run test asserts `writer.total_rows == 0`
   (trivially true) and the "write mode" test only asserts `SystemExit(1)` on failure. No test shows
   `main()` appending rows through the writer. Need a test with a fetchable filing body asserting
   `writer.total_rows > 0` in write mode, and that the fakes were actually called. Spark adapter
   classes themselves (`SparkDataWriter` etc.) are untested (acceptable only if a live WSL check is done).
4. Placeholder User-Agents (PARTIAL).
   - `xbrl_client.py` (lazy `_get_user_agent`, raises on missing/"example"), `config/settings.py`, notebook (raises) are fixed.
   - The notebook does NOT delegate to `pipelines/sec_rag_ingest.py`: only a DEPRECATED banner was added;
     its own `UNIVERSE_STK` and ingestion remain (`notebooks/02_ingest_sec_edgar.py`). Request said it must delegate.
   - `notebooks/refresh_bronze_cot.py:69` still has `contact@example.com` (COT, outside RAG scope, but "anywhere").
   - The grep-style test only scans a hardcoded 7-file list (`TestNoPlaceholderUserAgent`), which excludes
     the notebook and `notebooks/`; it also silently skips non-existent files.
5. Accession conflict (PARTIAL). `test_different_cik_accession_raises_value_error` covers the first anti-join path,
   which raises at `sec_rag_ingest.py:1007`, outside the per-filing try. The race-path conflict (`:1066`) is
   inside the try and untested. The `except ValueError: raise` (`:1128`) is broader than "conflict only"
   (re-raises any ValueError). Mutation (remove that clause, /tmp/ragcov-mut-5): all 66 tests PASS, so
   the fix is unproven. Add a race-path test (accession_reader returning different results on 2nd call) and
   narrow to a dedicated `AccessionOwnershipError`.
6. Docs (PARTIAL). `gold_sec_coverage` (7 cols) matches `gold/07_gold_sec_coverage.sql`; `sec_ingest_log`
   (16 cols) matches `SparkLogWriter` fields. But `sec_cik_mapping_log` (docs/DATA_SCHEMAS.md ~495) has no
   writer anywhere in code: remove from docs or write it.
7. pyspark-hidden (PASS): 405 passed with pyspark hidden.

## Mutation summary
| Item | Mutation | Result |
|---|---|---|
| 1 | old serial hybrid_retriever | 2 coalescing tests fail; 3-ticker test passes (weak) |
| 2 | old serial build_sec_embeddings | concurrent test fails (good) |
| 3 | drop adapters from main() | all pass (NOT proven) |
| 5 | drop `except ValueError: raise` | all pass (NOT proven) |

## Required next round
Fix 1 (discriminating 3-ticker test), 3 (write-mode test proving rows written), 4 (notebook delegation or removal
+ broaden grep test), 5 (race-path test, narrow exception), 6 (sec_cik_mapping_log), plus rerun pandas-3 venv with deps installed.
