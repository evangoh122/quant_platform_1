# VERDICT: app-resilience-round2 — MiMo
**Status:** APPROVED
**Round:** 2

## Blocking findings
- None

## Non-blocking notes
- The 3 RAG test files (test_chat_engine.py, test_graph_rag_engine.py, test_langgraph_engine.py) have pre-existing import errors (`api.db` and `api.services.rag_engine` modules missing). These are not caused by this round's changes.
- Frontend build requires non-UNC working directory on Windows (esbuild postinstall issue). Built successfully via temp dir workaround.
- The circuit breaker's first request to a hanging DB will still be slow (the hang happens inside `_ensure_user` before the breaker can intercept). Subsequent requests are fast because the breaker opens. A future enhancement could add a connection-level timeout wrapper.

## Checks run
- `python -m pytest -q -m "not spark and not lakebase and not databricks" --timeout=30 --ignore=tests/rag --ignore=tests/bronze --ignore=tests/silver --ignore=tests/gold --ignore=tests/ml --ignore=tests/strategies` → **369 passed, 65 skipped, 0 failed**
- `npm ci && npm run build` (frontend/) → **built successfully** (dist/index.html + assets)
- `git log --oneline -5` → clean commit history on slice/app-frontend-deploy

## Changes committed

### Deploy fixes
1. **app.yaml**: Replaced `${DATABRICKS_APP_PORT:-8000}` with literal `8000` (Databricks Apps doesn't shell-expand)
2. **requirements.txt**: Removed `ibapi>=10.19.0` (not on PyPI), moved mlflow/langchain/polygon-api-client/yfinance/beautifulsoup4/lxml/pytest-timeout to `requirements-dev.txt`, added missing app deps (psycopg, tenacity, numpy, pandas, polars, openai, langchain-core, langchain-openai, huggingface-hub)

### Item 1: Lakebase auth resilience
3. **api/deps.py**: Added role cache (TTL 5 min), circuit breaker (3 failures → 30s cooldown), degraded mode for read routes, fast 503 for write routes when breaker open
4. **db/lakebase.py**: Reduced default connect timeout from 10s to 3s
5. **api/routes/health.py**: Reports circuit breaker status in health endpoint
6. **tests/api/test_resilience.py**: 9 tests covering breaker lifecycle, cache behavior, fast degradation
7. **tests/api/test_auth.py**: Updated existing test for new degraded-mode behavior
8. **tests/api/conftest.py**: Added breaker/cache reset between tests

### Item 2: Bounded market queries
9. **api/routes/market.py**: Default 252-day window (configurable `?days=N`, max 1000), explicit LIMIT (default 5000, max 5000)
10. **agent/tools_retrieval.py**: `get_market_features` and `get_options_features` accept `limit` param, select only needed columns
11. **db/delta_adapter.py**: `market_features` selects specific columns, applies LIMIT
12. **tests/api/test_market.py**: 7 tests verifying bounds, limits, param validation

### Item 3: Lakebase resource + deploy docs
13. **resources/app.yml**: Declared `database` resource with `evangoh-capstone-lakebase` instance
14. **docs/DEPLOYMENT.md**: Added Lakebase resource declaration section and required Postgres grants SQL