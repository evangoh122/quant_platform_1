# VERDICT: test-collection round 2 — Codex (blocker withdrawn on re-check → APPROVED)

CHANGES_REQUESTED

Blocking finding:

- [etl/extract_yfinance.py:18](/home/jianj/code/qp1-tests/etl/extract_yfinance.py:18) claims the default ticker universe was “inlined unchanged,” but it is behaviorally different from the prior `etl.bulk_load_massive.TICKERS` at commit `afc56c0`.
  - Previous: 32 tickers.
  - Current: 35 tickers.
  - Added: `GOOG`, `ONTO`, `SLAB`, `SNDK`, `STM`, `WOLF`.
  - Removed: `COHR`, `IIVI`, `OLED`.
  - Because [run_yf_bars_etl](/home/jianj/code/qp1-tests/etl/extract_yfinance.py:144) sorts and uses this set when no tickers are supplied, default behavior changed. Restore the exact prior universe or explicitly justify and test the migration.

Other validation:

- Hidden coverage is restored:
  - Persona rails: 14 runnable tests passed; only four `api.routes.conjoint` tests remain narrowly skipped at [test_persona_rails.py:15](/home/jianj/code/qp1-tests/tests/rag/test_persona_rails.py:15).
  - `_to_int`: runs and passes at [test_extract_cot.py:18](/home/jianj/code/qp1-tests/tests/test_extract_cot.py:18).
  - `_ms_to_iso`: both tests run and pass; DB-only tests are narrowly marked through [test_bronze_polygon_bars.py:24](/home/jianj/code/qp1-tests/tests/bronze/test_bronze_polygon_bars.py:24).
  - No remaining skip in the reviewed files is broader than its removed dependency.
- The false “consolidated” reason is corrected to “removed; not carried forward” at [test_extract_polygon_ticks.py:6](/home/jianj/code/qp1-tests/tests/test_extract_polygon_ticks.py:6).
- All six extractor modules import successfully. Calling each `_get_connection()` without `db.database` raises the actionable `RuntimeError`: “DuckDB local store was retired; production ingestion writes Delta via notebooks/01_ingest_market_data.py.” No `NameError` or silent no-op observed.
- No test was deleted and no assertion was weakened in `fa90d99..HEAD`; changes split dependency-specific skips from still-valid tests.

Required commands:

- `python3 -m pytest --co -q`: 371 collected, 0 errors.
- `python3 -m pytest -q -m 'not spark and not lakebase and not databricks'`: 289 passed, 67 skipped, 16 deselected, 12 failed.
- All 12 failures are the previously attributed empty sentiment-dictionary failures; none arise from this round’s changes.


APPROVED

The correct baseline for “unchanged behaviour” is IBKR_workbench commit `b5b7b5a`, the module originally imported by `extract_yfinance.py`.

Evidence:

- Its `TICKERS` set contains 35 unique symbols.
- `_DEFAULT_TICKERS`/`SEMI_TICKERS` matches that set exactly: no missing or additional symbols.
- `b5b7b5a` is an ancestor of the current IBKR_workbench `HEAD`.
- The source file has no tracked working-tree modifications.
- `afc56c0` contains a self-described 32-ticker stub, belongs only to `fix/test-harness`, and is not an ancestor of `main`.
- Compared with the real source, that stub adds `COHR`, `IIVI`, and `OLED`, while omitting `GOOG`, `ONTO`, `SLAB`, `SNDK`, `STM`, and `WOLF`.
- Latest commit `00b74d1` accurately pins and explains the source provenance.

The previous ticker-list blocker is withdrawn.

