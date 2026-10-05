# VERDICT: rag-coverage — MiMo
**Status:** APPROVED
**Round:** 2

## Blocking findings
None.

## Non-blocking notes
- `test_chat_engine.py`, `test_graph_rag_engine.py`, `test_langgraph_engine.py` have collection errors (pre-existing, unrelated to this change — missing deps like `openai` or `neo4j`).
- Pre-existing ruff warnings in `agent/tools_retrieval.py` (unused imports) and `tests/rag/test_embedding_config.py` (unused `os` import) — not introduced by this change.
- The `accepted_ts` epoch parsing test (`test_old_code_fails_in_sgt`) demonstrates the timezone bug was already fixed in a prior round; the current code is correct.

## Checks run
- `python -m pytest -q -p no:cacheprovider --timeout=60 tests/rag --ignore=tests/rag/test_chat_engine.py --ignore=tests/rag/test_graph_rag_engine.py --ignore=tests/rag/test_langgraph_engine.py` → 383 passed, 16 skipped, 17.8s
- `python -m ruff check pipelines/sec_rag_ingest.py pipelines/build_sec_embeddings.py api/services/hybrid_retriever.py tests/rag/test_sec_rag_ingest.py tests/rag/test_sec_retrieval_tool.py tests/rag/test_sec_embeddings_incremental.py tests/rag/test_sec_coverage_sql.py` → All checks passed
- `git diff --stat origin/slice/rag-coverage -- tests/` → 22 files changed, 3789 insertions(+), 444 deletions(-). No large deletions in test_hybrid_retriever.py (123 lines net change, 87→87 test functions preserved).
- `git diff --check` → clean
- `.agents/dispatch.sh` untouched (verified via git diff)

## Test count
- Base branch (origin/slice/rag-coverage): 370 test functions in tests/rag
- Current: 455 test functions in tests/rag (+85 new)
- test_hybrid_retriever.py: 87 test functions (preserved from base)

## Commits
- `b795034` feat(ingest): SEC RAG ingestion pipeline + CIK mapping + tests (step a)
- `7f92828` feat(retriever): per-ticker LRU cache + NoCoverageError/TickerRequiredError (step b)
- `d0ffe30` feat(embeddings+silver+coverage): incremental embeddings, anti-join, coverage table, tests (steps c-e)

## Changed files
- `pipelines/sec_rag_ingest.py` — Pure-core SEC EDGAR ingestion with dependency injection (1178 lines)
- `pipelines/_http_adapter.py` — Production HTTP adapter (27 lines)
- `pipelines/build_sec_embeddings.py` — Anti-join incremental embedding builder with CLI flags
- `api/services/hybrid_retriever.py` — Per-ticker LRU cache (32 default), TickerCorpus dataclass, NoCoverageError/TickerRequiredError, global corpus fallback for backward compat
- `agent/tools_retrieval.py` — Catches NoCoverageError/TickerRequiredError before fallback
- `silver/05_silver_sec_sections.sql` — Source anti-join for idempotent ingestion
- `silver/06_silver_sec_entities.sql` — Source anti-join for idempotent ingestion
- `gold/07_gold_sec_coverage.sql` — Coverage table (ticker, cik, n_filings, n_chunks, etc.)
- `pipelines/run_silver_gold.py` — Added gold_sec_coverage step
- `resources/jobs.yml` — sec_embeddings + sec_rag_ingest jobs (manual only, no schedule)
- `docs/SEC_RAG_COVERAGE_RUNBOOK.md` — Live runbook with dry-run, pilot, verification SQL
- `tests/rag/conftest.py` — psycopg mocks, LRU cache cleanup autouse fixture
- `tests/rag/test_sec_rag_ingest.py` — 44 tests: CIK mapping, rate limiter, filing discovery, idempotency, golden parity
- `tests/rag/test_sec_retrieval_tool.py` — 5 tests: no_coverage, ticker_required, retrieval_unavailable errors
- `tests/rag/test_sec_embeddings_incremental.py` — 9 tests: anti-join, batch, dimension validation, YAML assertions
- `tests/rag/test_sec_coverage_sql.py` — 9 tests: static SQL contract checks
- `tests/rag/test_hybrid_retriever.py` — 87 tests (preserved), 2 modified for PIT behavior + anti-join API
- `tests/rag/fixtures/sec/` — 4 fixture files (tickers, submissions, filing HTML)

## Key design decisions
1. **Per-ticker LRU with global fallback**: `get_ticker_corpus()` first checks LRU cache, then falls back to global corpus state (for backward compat with tests that monkeypatch globals), then loads from Spark. Empty corpus returned when global is loaded but ticker not found (prevents Spark connection hang).
2. **PIT filter change**: Missing/null `accepted_ts` chunks are now EXCLUDED (was defensively included). Per spec: "all newly published chunks require authoritative acceptance time."
3. **Anti-join pattern**: Both silver transforms and embedding builder use Spark LEFT ANTI JOIN instead of collecting all IDs into driver memory.
4. **Embedding MERGE**: Changed from `WHEN MATCHED THEN UPDATE SET *` to only `WHEN NOT MATCHED THEN INSERT *` (append-only per spec).
5. **Rate limiter uses injectable clock**: All tests use FakeClock — no real sleep anywhere.

## Live-run handoff
Run in order:
1. `databricks bundle deploy -t dev`
2. `databricks bundle run -t dev sec_rag_ingest -- --dry-run --start-date 2024-09-01 --forms 10-K,10-Q`
3. `databricks bundle run -t dev sec_rag_ingest -- --tickers "$PILOT_TICKERS" --start-date 2024-09-01`
4. `databricks bundle run -t dev silver_gold_refresh`
5. `databricks bundle run -t dev sec_embeddings -- --ticker "$PILOT_TICKERS" --batch-size 256 --partitions 4`
6. Run verification SQL from docs/SEC_RAG_COVERAGE_RUNBOOK.md

Requires `SEC_EDGAR_USER_AGENT` env var set to a descriptive contact string (never commit the value).