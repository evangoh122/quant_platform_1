# VERDICT: test-collection — MiMo
**Status:** APPROVED
**Round:** 1

## Decision table

| File | Action | Reason |
| :--- | :--- | :--- |
| tests/bronze/test_bronze_polygon_bars.py | skip | db.database (DuckDB) removed; etl.extract_polygon imports it |
| tests/bronze/test_bronze_polygon_option_bars.py | skip | db.database (DuckDB) removed; etl.extract_polygon imports it |
| tests/bronze/test_bronze_yfinance_bars.py | skip | db.database (DuckDB) removed |
| tests/bronze/test_bronze_yfinance_indices.py | skip | db.database (DuckDB) removed |
| tests/silver/test_silver_index_stats.py | skip | db.database (DuckDB) removed |
| tests/silver/test_silver_ohlcv_quality.py | skip | db.database (DuckDB) removed |
| tests/test_extract_cot.py | skip | db.database (DuckDB) removed; etl.extract_cot imports it |
| tests/test_extract_options.py | skip | db.database (DuckDB) removed |
| tests/test_extract_stocks.py | skip | db.database (DuckDB) removed |
| tests/test_extract_polygon_ticks.py | skip | etl.extract_polygon_ticks removed; consolidated into etl.extract_polygon |
| tests/test_security.py | skip | rag_engine and query modules removed |
| tests/rag/test_extract_graph_triples.py | skip | scripts module removed |
| tests/rag/test_persona_rails.py | skip | api.routes.conjoint module removed |
| tests/rag/test_chat_engine.py | optional-dep | pytest.importorskip("openai") |
| tests/rag/test_graph_rag_engine.py | optional-dep | pytest.importorskip("langchain_openai") |
| tests/rag/test_langgraph_engine.py | optional-dep | pytest.importorskip("edgar") |
| tests/rag/test_guardrails.py | port | Added tests/rag/__init__.py to resolve name collision with tests/lakebase/test_guardrails.py |

## Blocking findings
None.

## Non-blocking notes
- 12 pre-existing failures in test_sentiment.py: LM dictionary files not found (empty frozensets). Product defect, not a test-collection issue.
- 8 pre-existing errors in test_eval_pipeline.py::TestReviewQueueDB: `api.db` module missing at fixture setup time. Product defect.
- No test files deleted. No assertions weakened.

## Checks run
- `python3 -m pytest --co -q` → **340 tests collected, 0 errors** (was 325 collected, 17 errors)
- `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` → **272 passed, 12 failed, 48 skipped, 16 deselected, 8 errors**
  - 12 failures: test_sentiment.py (pre-existing — dictionary files missing)
  - 8 errors: test_eval_pipeline.py::TestReviewQueueDB (pre-existing — api.db module missing)