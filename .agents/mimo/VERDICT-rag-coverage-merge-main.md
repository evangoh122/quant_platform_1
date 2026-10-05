# VERDICT: rag-coverage-merge-main — MiMo
**Status:** APPROVED
**Round:** 1

## Blocking findings
- None

## Non-blocking notes
- The merge resolved conflicts in `api/services/hybrid_retriever.py` and `README.md`
- Per-ticker design preserved with LRU cache; Spark-then-warehouse fallback added to `_load_ticker_corpus`, `_load_alias_map`, `check_ticker_coverage`
- `_get_spark()` semantics from main preserved (ambient session when `DATABRICKS_RUNTIME_VERSION` is set, otherwise `DatabricksSession`)
- Startup warm-up updated to warm alias map/coverage instead of full corpus
- `repair_cik_ownership` now uses `SELECT DISTINCT accession_number, cik` for one UPDATE per filing
- `repair_cik_ownership` now rewrites `filing_url` to `.../edgar/data/{int(correct_cik)}/...`
- Warehouse SQL binds ticker as parameter (no f-string user values); table names are constants

## Checks run
- `python -m pytest -q -m "not spark and not lakebase and not databricks" tests/rag/test_sec_rag_ingest.py -k "TestRepairCikOwnership"` → 10 passed
- `python -m pytest -q -m "not spark and not lakebase and not databricks" tests/rag/test_hybrid_retriever.py` → 114 passed
- `python -m pytest -q -m "not spark and not lakebase and not databricks" tests/agent/` → 49 passed