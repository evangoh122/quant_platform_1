
Status: CHANGES_REQUESTED

Reviewed cumulative HEAD `c841f53` on `slice/app-resilience-round11`, 10 commits ahead of `slice/app-frontend-deploy`.

Findings:

1. Blocking — market source labels remain incorrect. Daily OHLCV comes from `silver_ohlcv_day_adjusted`, but [api/routes/market.py:64](/home/jianj/code/qp1-appfe/api/routes/market.py:64), [api/routes/market.py:86](/home/jianj/code/qp1-appfe/api/routes/market.py:86), and [api/routes/market.py:87](/home/jianj/code/qp1-appfe/api/routes/market.py:87) still report `gold_ohlcv_features`. The dashboard empty-state message also names the gold table at [MarketDashboard.tsx:85](/home/jianj/code/qp1-appfe/frontend/src/screens/MarketDashboard.tsx:85). Round 9 explicitly required all source labels to be corrected.

2. Blocking test survivor — the smoke rejection tests pass for the wrong reason. [tests/test_smoke_app.py:93](/home/jianj/code/qp1-appfe/tests/test_smoke_app.py:93) and [tests/test_smoke_app.py:112](/home/jianj/code/qp1-appfe/tests/test_smoke_app.py:112) mock only `/`; subsequent API requests at [scripts/smoke_app.py:133](/home/jianj/code/qp1-appfe/scripts/smoke_app.py:133) fail and force the overall result to `False`. An archive mutation making `_check_frontend_build()` unconditionally return `True` still produced `2 passed`. The current production helper itself was directly probed and correctly rejects the missing-frontend JSON response, but that behavior is not load-bearing in the tests.

3. Blocking test gap — the required frontend behavior tests were not added. [frontend/package.json:6](/home/jianj/code/qp1-appfe/frontend/package.json:6) has no test runner. Both archive mutations below passed a clean install/build:

   - Replacing the max-date reducer at [MarketDashboard.tsx:32](/home/jianj/code/qp1-appfe/frontend/src/screens/MarketDashboard.tsx:32) with `data[0]`.
   - Replacing the Lakebase health calculation at [App.tsx:52](/home/jianj/code/qp1-appfe/frontend/src/App.tsx:52) with `false`, permanently suppressing the banner at [App.tsx:81](/home/jianj/code/qp1-appfe/frontend/src/App.tsx:81).

Current production behavior is correct: an unsorted-date probe selected `2025-12-31` as the OHLCV maximum, and daily/options SQL orders `event_date`/`feature_ts` descending. However, the round-9 requirements explicitly called for frontend tests proving max-date selection and the global banner.

Mutation results:

- Killed: no `pool.open`; no token-mint timeout; no semaphore acquire; semaphore double release; connection establishment outside timeout; invalid intraday `open`; removed daily/options ordering; hardcoded development schema; removed `databricks-sql-connector`; partition-row filtering removed; `UUP` restored to uppercase `FX`.
- Survived: smoke frontend-check bypass; max-date reducer removal; Lakebase banner disablement; source-label regression.

Validation:

- DeepSeek prerequisite: APPROVED.
- Focused historical regression suite: `18 passed`.
- Semaphore/pool/token focused suite: `5 passed`.
- `npm ci --ignore-scripts && npm run build`: passed; 48 modules built.
- Exact full pytest command was run but did not close or emit results in this sandbox and was interrupted after stalling. The supplied independent Claude run reports `1550 passed`.
- `git diff --check`: passed.
- Worktree remained clean; no repository files were edited.

