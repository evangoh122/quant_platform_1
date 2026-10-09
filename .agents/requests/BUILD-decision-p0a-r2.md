# Build: Decision Dashboard Phase 0a round 2 (DeepSeek CHANGES_REQUESTED)

Builder: MiMo. Base: HEAD aacee9c on `feat/decision-dashboard-p0`. Findings: `.agents/deepseek/VERDICT-decision-p0a.md`. Commit on this branch only; no deploy/live data/new deps.

## Required
1. **Blocking (B1):** `db/delta_adapter.py:457` (`market_features_daily`, PySpark branch) does `df.limit(limit)` with no `orderBy`; its warehouse fallback orders `event_date DESC`
   (`_build_market_features_daily_query`). Add `.orderBy(F.col("event_date").desc())` before `.limit`. Audit the other unordered Spark limits in `db/delta_adapter.py`
   (~lines 401, 475, 508) and `agent/tools_retrieval.py:117` is already fixed: for each one that reads a time series where the matching warehouse query is newest-first,
   add the same ordering using the column the warehouse query orders by. Leave `.limit(1)` single-row lookups alone unless the warehouse variant orders them (then order them
   too, e.g. `get_cot_positioning`). List every site you changed or deliberately left, with reason, in the evidence file.
2. **Tests (mandatory shape):** one test per changed site that calls the real production function with a recording Spark stub (`_has_pyspark=True`, stubbed `_spark()`),
   asserting `orderBy` with a DESCENDING column of the right name happens BEFORE `limit`. Do not copy production logic.
3. **Mutation harness honesty:** `.agents/run-mutations.py` uses `--noconftest`, which can false-positive M2/M3 (missing `fake_lakebase`). Remove `--noconftest`
   (fix the harness so it works with conftest) and make M4 fail via the semantic NULL assertion, not a parser error (adjust the test or the mutation so the SQL still parses).
4. Fix the `api/trading_days.py` docstring that claims the window is "inclusive of end" if that is inaccurate.

## Mutations that MUST fail a test (isolated `git archive` copies; record transcript)
M1-M5 from the original request (re-run all five) plus M6: remove the new `orderBy` from `market_features_daily`; M7: reverse the order direction on one of the other changed sites.

## Acceptance
`python3 -m pytest tests/api tests/gold tests/agent -q` passes; frontend `npx tsc --noEmit`, `npx vitest run`, `npm run build` pass (Linux node: `export PATH="$HOME/.nvm/versions/node/v26.5.0/bin:$PATH"`).
Evidence to `.agents/mimo/VERDICT-decision-p0a-r2.md`. Commit. End with exactly:
`BUILD DONE | status: <SUCCESS|FAILURE> | sha: <40-char SHA or NO_COMMIT> | branch: feat/decision-dashboard-p0 | evidence: .agents/mimo/VERDICT-decision-p0a-r2.md`
