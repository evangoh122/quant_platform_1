# BUILD-REQUEST: test-collection — ROUND 2 (narrow the skips; make ETL importable)

**Branch:** `fix/test-collection` · **Builder:** MiMo · **Validators:** Claude, then Codex
Read `.agents/codex/VERDICT-test-collection.md`. Codex confirmed: 0 collection errors, no
deleted tests, no weakened assertions, optional-dependency skips correct, and the 12
sentiment failures are correctly attributed (dictionary file arrives with PR #8 — leave them).

## Problem: whole-file skips hide coverage of code that still exists

| File | What is hidden | Still exists at |
| :-- | :-- | :-- |
| `tests/rag/test_persona_rails.py:2` | `check_persona_fit`, `_has_financial_figure` tests (lines 39–153) | `api/services/guardrails/persona_rails.py:98, :173` |
| `tests/test_extract_cot.py:6` | `_to_int` test (lines 27–33) | `etl/extract_cot.py:140` |
| `tests/bronze/test_bronze_polygon_bars.py:12` | `_ms_to_iso` test (lines 67–75) | `etl/extract_polygon.py:431` |

Also `tests/test_extract_polygon_ticks.py:6` gives a false reason ("consolidated into
`etl.extract_polygon`" — it was not; it was removed). Correct the reason.

## Root cause in production code (fix it — minimal)

**All six ETL modules import the removed `db.database` at module top level**, so none can be
imported on `main`: `etl/extract_polygon.py:19`, and the same in `extract_options`,
`extract_edgar`, `extract_cot`, `extract_yfinance`, `extract_stocks`.

Fix minimally: move `from db.database import get_connection` from the top of each module
**into the functions that write to the database**. The module then imports; pure helpers are
testable; DuckDB write paths fail only when called. Where a function calls it, make the
failure explicit and actionable (raise `RuntimeError("... DuckDB local store was retired;
production ingestion writes Delta via notebooks/01_ingest_market_data.py ...")` if the import
fails). **Do not** port these modules to Delta and **do not** recreate `db/database.py`.

## Then narrow the skips
- Skip **only** the tests that need DuckDB or the removed route — use per-test or per-class
  `@pytest.mark.skip(reason=...)`, not module-level skips.
- Every test of a pure helper whose code exists must **run and pass**. List them.
- For each file in the table, paste before/after: tests run vs skipped.

## Acceptance
- `python3 -m pytest --co -q` → 0 errors.
- `python3 -c "import etl.extract_polygon, etl.extract_options, etl.extract_edgar, etl.extract_cot, etl.extract_yfinance, etl.extract_stocks"` succeeds.
- `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` → only the 12
  known sentiment failures remain; more tests pass than before (was 272). Paste it.

Do not touch `ml/`, `silver/`, `gold/`, `agent/`, `db/`, `api/` (tests only),
`.agents/dispatch.sh`. Production changes limited to the six `etl/` import moves.
**Commit your work.** Write `.agents/mimo/VERDICT-test-collection-round2.md`.
