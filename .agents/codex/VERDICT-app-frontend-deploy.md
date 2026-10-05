
Status: CHANGES_REQUESTED

Findings:

1. Blocking — Lakebase can never establish a healthy pool. [db/lakebase.py](/home/jianj/code/qp1-appfe/db/lakebase.py:155) creates `ConnectionPool(open=False)` and immediately calls `wait()`. A direct probe raises `PoolClosed: the pool ... is not open yet`. Consequently, role resolution always degrades to viewer and every write remains unavailable. The fake at [tests/api/test_resilience.py](/home/jianj/code/qp1-appfe/tests/api/test_resilience.py:335) does not model this required open state. Additionally, token minting at [db/lakebase.py](/home/jianj/code/qp1-appfe/db/lakebase.py:59) has no subprocess timeout, so total connection establishment is not bounded.

2. Blocking — warehouse concurrency is not actually bounded. On timeout, [db/delta_adapter.py](/home/jianj/code/qp1-appfe/db/delta_adapter.py:199) raises while the worker may remain alive, then releases the semaphore at line 224. With a semaphore size of two, eight sequential queries whose cursors ignored cancellation produced eight live workers. Disabling semaphore acquisition also survived `test_warehouse_query_semaphore_bounded`; its assertion at [tests/api/test_health_diagnostics.py](/home/jianj/code/qp1-appfe/tests/api/test_health_diagnostics.py:959) never verifies the number of executions. Connection creation and its synchronous liveness query also occur before the timeout boundary at [db/delta_adapter.py](/home/jianj/code/qp1-appfe/db/delta_adapter.py:109).

3. Blocking — the deployment smoke test does not verify that the frontend was shipped. [scripts/smoke_app.py](/home/jianj/code/qp1-appfe/scripts/smoke_app.py:71) accepts the missing-build JSON hint and even arbitrary non-HTML content as `PASS`. A mocked run with arbitrary root bytes and valid JSON APIs returned `True`. This defeats the central frontend-deployment smoke check.

4. Blocking — schema-contract coverage is disconnected from the actual SQL. [db/schema_contract.py](/home/jianj/code/qp1-appfe/db/schema_contract.py:52) maintains a second manual list, while the test only validates that list. Mutating the real intraday query at [db/delta_adapter.py](/home/jianj/code/qp1-appfe/db/delta_adapter.py:415) to select invalid column `open` still passed `test_schema_contract_passes`.

5. Blocking data correctness — daily and options queries have no descending ordering before `LIMIT`: [db/delta_adapter.py](/home/jianj/code/qp1-appfe/db/delta_adapter.py:397) and [agent/tools_retrieval.py](/home/jianj/code/qp1-appfe/agent/tools_retrieval.py:88). The frontend treats row zero as the latest market/options observation at [MarketDashboard.tsx](/home/jianj/code/qp1-appfe/frontend/src/screens/MarketDashboard.tsx:32). Therefore the displayed “latest” values can be arbitrary or stale. DeepSeek’s options-ordering note is blocking in this usage.

6. The required account-services banner is absent. Only [SystemHealth.tsx](/home/jianj/code/qp1-appfe/frontend/src/screens/SystemHealth.tsx:68) fetches health and renders a dependency card; [App.tsx](/home/jianj/code/qp1-appfe/frontend/src/App.tsx:32) does not surface “Account services unavailable” when Lakebase is down.

7. Deployment configuration still pins the development schema in [app.yaml](/home/jianj/code/qp1-appfe/app.yaml:9), while the bundle path uses `${var.schema}`. Direct/UI deployment via `app.yaml` can therefore read the personal development schema in production.

Mutation results:

- Survived: invalid real warehouse column; disabled semaphore acquisition; removed `databricks-sql-connector` from requirements.
- Killed correctly: appending `LIMIT` to `DESCRIBE`; restoring `%s` warehouse parameters.
- The requirements survivor occurs because [tests/test_requirements_completeness.py](/home/jianj/code/qp1-appfe/tests/test_requirements_completeness.py:91) truncates `databricks.sql` to `databricks`, making its connector-specific mapping unreachable.

Non-blocking items confirmed:

- [scripts/check_schema_contract.py](/home/jianj/code/qp1-appfe/scripts/check_schema_contract.py:30) includes Delta partition-description rows as columns.
- [db/schema_contract.py](/home/jianj/code/qp1-appfe/db/schema_contract.py:112) maps `UUP` to uppercase `FX`; a direct probe queried `mapped_asset='FX'` and returned empty.
- Market source labels still say `gold_ohlcv_features` although daily data comes from `silver_ohlcv_day_adjusted`.

Validation:

- DeepSeek prerequisite verdict: APPROVED.
- Focused non-TestClient checks: `9 passed`.
- Required full pytest command: did not complete after ten minutes. A verbose focused run stopped at the first TestClient health test; direct invocation of the same health logic returned in `5.005s`.
- Exact `npm ci`: sandbox failure in esbuild postinstall (`spawnSync ... EPERM`, Node 26.5.0).
- After `npm ci --ignore-scripts`, TypeScript compilation and `npm run build` passed; Vite built 48 modules in 1.50s.
- `git diff --check`: passed. No tracked files were modified.

