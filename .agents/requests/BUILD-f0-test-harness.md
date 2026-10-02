# BUILD-REQUEST: f0-test-harness

**Round:** 1
**Branch:** `fix/test-harness` (branch off `main`)
**Agent:** MiMo (builder)
**Priority:** BLOCKING — every other lane's acceptance gate depends on this.

---

## The defect

`pytest` cannot collect a single test in this repo. Reproduce:

```
cd <repo> && python3 -m pytest -q --co
# ImportError while loading conftest '<repo>/conftest.py'
# conftest.py:48: in <module>
#     import db.database as db_module
# E   ModuleNotFoundError: No module named 'db.database'
```

`conftest.py` is a leftover from the `IBKR_workbench` repo, which stored data in
DuckDB. It imports `db.database` and exposes DuckDB-based fixtures (`tmp_db`,
`db_conn`) that call `db_module.init_db()` and `db_module.get_connection()`.
That module was never carried over by the merge. `db/` now contains only
`__init__.py` and `delta_adapter.py`. Per `MERGE_PLAN.md`, `delta_adapter.py` is
the Spark/Delta replacement for DuckDB's `get_connection()`.

So there are 34 test files, none of which can run.

## Scope — what to fix

### 1. Repair `conftest.py`

- Remove the dead `db.database` import and the DuckDB-era fixtures, **or**
  reimplement them against the current storage layer — whichever leaves the
  existing 34 test files able to collect.
- Keep the `_make_ibapi_stubs()` logic. It is doing real work: `ibapi` is not
  pip-installable and the stubs must stay real classes, not MagicMocks, or
  `IBKRClient` hits a metaclass conflict. Do not "simplify" it into mocks.
- Decide per test file whether it needs a storage fixture at all. Many are pure
  logic tests (`test_slippage.py`, `test_tickers_config.py`, `test_security.py`)
  and should need no database.
- Tests that genuinely require Spark or a live service must be marked so they
  can be deselected (see §3), not left to fail.

### 2. Pin and document dependencies

- `requirements.txt` currently lists runtime deps but **no test deps at all**.
  Add a `requirements-dev.txt` with at minimum: `pytest`, `pytest-mock`,
  `psycopg[binary]`, `psycopg-pool`, `pyspark`, `mlflow`, `scikit-learn`,
  `xgboost`, `pandas`, `pyarrow`.
- **Record the install incantation for this machine.** Plain `pip install` fails
  here with PEP 668 (externally-managed environment) and `python3 -m venv` fails
  (no `ensurepip`). The working form is:
  ```
  pip install --user --break-system-packages -r requirements-dev.txt
  ```
  Put this in `README.md` under a "Development setup" heading. Four agents
  across two lanes are about to hit this; document it once.

### 3. Test markers

Register markers in `pytest.ini` so slices can deselect what they can't run:

- `spark` — needs a local SparkSession
- `lakebase` — needs the live Lakebase Postgres instance
- `databricks` — needs a live Databricks workspace/warehouse
- `slow`

`python3 -m pytest -q -m "not spark and not lakebase and not databricks"` must
pass cleanly and be the documented default for fast feedback.

## Non-goals — do not do these

- Do not write new feature code. No Lakebase schema, no ML, no streaming.
- Do not modify `db/delta_adapter.py`, `agent/`, `etl/`, or `services/` logic.
  Another lane owns those files right now and you will cause a merge conflict.
- Do not delete tests to make the suite green. A test that reveals a real gap
  should be marked `xfail` with a reason, not removed.
- Do not touch `.agents/`.

## Acceptance criteria

1. `python3 -m pytest -q --co` collects without error — paste the real count.
2. `python3 -m pytest -q -m "not spark and not lakebase and not databricks"`
   runs to completion. Paste the actual command and the actual summary line.
   Any failure that is a pre-existing product defect rather than a harness
   defect: list it explicitly in your verdict instead of hiding it.
3. `requirements-dev.txt` exists; `README.md` documents the install command.
4. Markers registered in `pytest.ini`; no `PytestUnknownMarkWarning`.
5. Only these files changed: `conftest.py`, `pytest.ini`, `requirements-dev.txt`,
   `README.md`, and test files you re-marked. Nothing else.

## When finished

Write your verdict to `.agents/mimo/VERDICT-f0-test-harness.md` per
`.agents/PROTOCOL.md`. State the honest before/after collect count and be
explicit about any test you marked rather than fixed.
