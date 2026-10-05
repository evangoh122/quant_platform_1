# VERDICT: rag-coverage — MiMo
**Status:** APPROVED
**Round:** 2

## Blocking findings
None

## Non-blocking notes
All9 CodeRabbit findings addressed:

1. **pipelines/sec_rag_ingest.py:1682** — FIXED: Replaced per-filing full-table read with `read_existing_accession()` single-accession lookup (parameterized). Added method to `ExistingAccessionReader` protocol and `SparkAccessionReader`. Updated `FakeAccessionReader` and `RaceAccessionReader` in tests.

2. **pipelines/sec_rag_ingest.py:1593** — FIXED: Now uses `accession_discovery_cik` dict to track which CIK discovered each filing during the discovery loop. Fallback branch uses `discovery_cik or next(iter(ticker_ciks))` instead of arbitrary set member.

3. **hybrid_retriever.py:788** — FIXED: Added `_alias_map_loaded` to `global` declaration in `reload_corpus()`. Now the reset on line790 correctly modifies the module-level variable.

4. **hybrid_retriever.py:770** — FIXED: Per-ticker invalidation now resolves alias via `_resolve_canonical_ticker(ticker)` before popping from cache. `GOOGL` correctly resolves to `GOOG` before cache removal.

5. **hybrid_retriever.py:191** — FIXED: `_get_embedding_model()` now uses provider-aware resolution matching `vector_search()`: checks `config.EMBEDDING_PROVIDER` to select `ST_EMBEDDING_MODEL` or `HF_EMBEDDING_MODEL`.

6. **api/main.py:305** — NOT VALID: The warm-up function already correctly loads the alias map via `_load_alias_map()` in a daemon thread with proper exception handling. No change needed.

7. **evals/rag_eval/corpus.py:489** — FIXED: Added offline alias map installation. Sets identity map from `ticker_docs` with `_alias_map_loaded = True` under `_alias_map_lock`. Restores originals in `finally` block.

8. **tests/rag/test_hybrid_retriever.py:3362** — FIXED: Converted direct assignments to `monkeypatch.setattr()` for both `_resolve_canonical_ticker` and `_load_ticker_corpus`. Test now accepts `monkeypatch` parameter.

9. **docs/SEC_RAG_COVERAGE_RUNBOOK.md:44** — FIXED: Added variable definitions for `catalog`, `schema`, and `PILOT_TICKERS` before bash commands that use them.

## Checks run
- `python3 -m pytest tests/rag/test_sec_rag_ingest.py -v` → 200 passed
- `python3 -m pytest tests/rag/test_hybrid_retriever.py::TestAliasResolutionMutationProof -v` → 2 passed
- `python3 -m pytest -q -m "not spark and not lakebase and not databricks" --ignore=tests/ml/test_hardening.py` → 2414 passed,107 skipped,24 deselected