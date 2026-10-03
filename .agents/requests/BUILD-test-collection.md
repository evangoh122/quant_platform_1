# BUILD-REQUEST: test-collection

**Branch:** `fix/test-collection` (off `main`) · **Builder:** MiMo · **Validators:** Claude, then Codex

## Goal
`python3 -m pytest --co -q` on `main` reports **325 collected, 17 errors**. Make collection
clean — **0 errors** — without deleting coverage that still means something.

Measured causes:

```
9  No module named 'db.database'            (DuckDB-era tests from IBKR_workbench)
1  No module named 'scripts'
1  No module named 'rag_engine'
1  No module named 'openai'
1  No module named 'langchain_openai'
1  No module named 'etl.extract_polygon_ticks'
1  No module named 'edgar'
1  No module named 'api.routes.conjoint'
```

## Rules
1. **Do not revive DuckDB.** `db/database.py` was removed on purpose; Delta is the store.
   (A previous attempt recreated it and was rejected.)
2. For each failing file decide, and record the decision per file in your verdict:
   - **Port** — if the code under test still exists and the test is meaningful, point it at
     the current module (e.g. `db.delta_adapter`, the current ETL module name).
   - **Skip with reason** — if the module under test no longer exists, use
     `pytest.importorskip(...)` or a module-level `pytest.skip(reason=..., allow_module_level=True)`
     naming what was removed and why. Never a bare skip.
   - **Optional dependency** — for `openai`, `langchain_openai`, `edgar`: use
     `pytest.importorskip("<pkg>")` so the tests run when the package is installed.
3. Do not delete test files. Do not weaken assertions in tests that already collect.
4. Do not edit production code to make a test import work, except to fix a genuinely wrong
   import path in a test.

## Acceptance
- `python3 -m pytest --co -q` → **0 errors**. Paste the summary line.
- `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` → paste summary;
  list any failures as pre-existing product defects rather than hiding them.
- A table in your verdict: file → port / skip / optional-dep → reason.

Do not touch `ml/`, `silver/`, `gold/`, `agent/`, `db/`, `api/` (except test-only import
paths), `.agents/dispatch.sh`. **Commit your work.** Write `.agents/mimo/VERDICT-test-collection.md`.
