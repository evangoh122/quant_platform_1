===VERDICT START===
# VERDICT: rag-coverage-round7 — DeepSeek (checker)
**Status:** APPROVED
**Round:** 7

## Summary

The round-6 blocking finding (module-level `sys.modules.setdefault("databricks" / "databricks.connect", MagicMock())` in `tests/rag/test_sec_rag_ingest.py:26-27` polluting `sys.modules` and corrupting the COT `spark` session fixture) is fixed. All acceptance criteria are met. Findings below are non-blocking only.

## Blocking findings

None.

## Non-blocking notes

1. **[test_sec_rag_ingest.py:979-980] the `_restore_pyspark_types` `setdefault` loop leaks real pyspark submodules (benign).** The finally block uses `sys.modules.setdefault(k, v)`, so after `import pyspark.sql.types` (line 975) re-populates `pyspark`, `pyspark.sql`, and `pyspark.sql.types` as *real* modules, `setdefault` does NOT restore the mocks for those three keys — the comment "Restore mocks for other tests" (line 978) is not achieved for them. More importantly, the real `import pyspark.sql.types` loads ~120 pyspark submodules that are *not* in the module-scoped `_mock_pyspark` fixture's `_patches`, so they survive the module teardown. Verified empirically (leakcheck plugin after `test_sec_rag_ingest.py test_zz_isolation.py`): ~120 `pyspark.*` keys remain in `sys.modules`, **0 of them MagicMock**, `databricks.connect == None`. Consequence: none of the leaked keys are `MagicMock`, so the isolation guard still passes and no downstream suite is affected (tests/bronze skips due to no *local* Spark regardless). This is a hygiene gap, not a Mock leak — hence non-blocking.

2. **[test_zz_isolation.py:14] `test_databricks_connect_not_polluted` references `MagicMock` incorrectly.** It uses `type(__import__("unittest.mock").MagicMock())`, but `__import__("unittest.mock")` returns the top-level `unittest` package, so `.MagicMock` raises `AttributeError` the moment the assertion's right-hand side is evaluated. In the no-leak case the test passes only because `mod is None` short-circuits the `or`. Under a real leak the test still FAILS (mutation proof below) — detection works — but with a confusing `AttributeError: module 'unittest' has no attribute 'MagicMock'` instead of the intended message. Compare `test_pyspark_not_polluted` (line 22) which correctly does `from unittest.mock import MagicMock`. Recommend fixing line 14 for a clean message; not blocking because the guard still fails on a leak.

3. **[test_sec_rag_ingest.py:69-80] dead real-types fallback in `_mock_pyspark`.** Because line 67 does an unconditional `sys.modules[name] = mock` *before* the `from pyspark.sql.types import (StringType …)` at lines 70-75, the import resolves against the mock and `_RealStringType` is always a `MagicMock`, never the real class — the `except ImportError` branch is unreachable. Harmless: the schema tests obtain real types via `_restore_pyspark_types` (line 975), not this block. Not blocking.

4. **[test_zz_isolation.py:26] missing trailing newline** (cosmetic only).

## Verified items (request checklist)

1. **Module fixture restores exactly.** `_mock_pyspark` (`test_sec_rag_ingest.py:48-89`) captures `_originals[name] = sys.modules.get(name)` (line 66) and on teardown pops names whose original was absent / restores names that existed (lines 85-89). Grep of `sys.modules` under `tests/rag/` shows no other *test module* performs module-level mutation — `test_hybrid_retriever.py` uses `patch.dict`/`monkeypatch.setitem` scoped inside tests, `test_sec_retrieval_tool.py` and `test_sec_rag_ingest.py` do it inside fixtures with teardown. The only module-level mutation is `conftest.py:mock_if_missing`, which is the intentional "mock only genuinely-missing modules" pattern (and only for psycopg/langgraph/etc., not pyspark/databricks). The setdefault loop leak is covered in note 1 (real modules only, no Mock leak).

2. **Isolation test detects the leak (mutation proof).** In `/tmp/ragcov-round7-mut`, re-added module-level `sys.modules.setdefault("databricks.connect", MagicMock())` + `sys.modules.setdefault("pyspark", MagicMock())`. `python3 -m pytest tests/rag/test_sec_rag_ingest.py tests/rag/test_zz_isolation.py -q` → **2 failed** (`test_databricks_connect_not_polluted`, `test_pyspark_not_polluted`), 82 passed. The guard genuinely fails on a Mock leak.

3. **COT spark fixture guard.** `tests/bronze/test_refresh_bronze_cot.py:43-66` now builds only `SparkSession.builder.master("local[2]")…getOrCreate()` (no `DatabricksSession` fallback), skips on any exception ("No local PySpark session available"), and then `if isinstance(session, MagicMock): pytest.skip(...)` (lines 64-65) as defense-in-depth. It still yields a real LOCAL `SparkSession` (not a `MagicMock`). It no longer creates a live Databricks serverless session.

4. **Comment fixed.** `pipelines/sec_rag_ingest.py:385` reads `status: str  # mapped | missing`; `grep -c 'ambiguous' pipelines/sec_rag_ingest.py` → `0`.

5. **No tests deleted/weakened.** `git diff 0f4cb1c..HEAD -- tests` touches only: `test_refresh_bronze_cot.py` (spark fixture only, 1 hunk), `test_sec_rag_ingest.py` (mock setup → fixture, 2 hunks), `test_sec_retrieval_tool.py` (mock setup → fixture, 1 hunk), and NEW `test_zz_isolation.py` (+2 tests). No `def test_*` added or removed in any existing file; net +2 tests.

## Decision on COT skip (per Claude's observation)

**Acceptable — consistent and network-free, not a weakening of the test code.** The 7 COT spark tests (`test_refresh_bronze_cot.py:223,239,252,373,389,402,423`) now SKIP with "No local PySpark session available", both combined and alone, because this machine's `pyspark` (v4.4.0.dev0) is the Databricks Connect shim: `SparkSession.builder.master("local[2]").getOrCreate()` raises `RuntimeError: Only remote Spark sessions using Databricks Connect are supported`. Round-6's "pass alone" was a latent bug — the removed `DatabricksSession` fallback silently created a LIVE serverless session (network/cost/nondeterminism in unit tests). No assertion was removed or relaxed (confirmed via diff), so the tests still run with full strength wherever a real local pyspark exists; on shim-only machines they now skip explicitly instead of doing network I/O. CI (no pyspark) skips identically. This is the correct hermetic trade-off; the residual gap is purely environmental coverage, not a code regression.

## Mutation proofs

- **Mock-leak re-added** (`/tmp/ragcov-round7-mut`, module-level `sys.modules.setdefault("databricks.connect"/"pyspark", MagicMock())`): `pytest tests/rag/test_sec_rag_ingest.py tests/rag/test_zz_isolation.py -q` → **2 failed, 82 passed** (`test_databricks_connect_not_polluted`, `test_pyspark_not_polluted`). Guard detects the leak. ✔

## Checks run

- `python3 -m pytest tests/rag tests/bronze -q -rs` → **583 passed, 36 skipped, 0 failed** (matches Claude's observation; 7 COT tests skip "No local PySpark session available")
- `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest tests/rag -q` → **423 passed, 19 skipped, 0 failed** (+2 vs round-6 = the two new isolation tests)
- `python3 -m pytest tests/rag/test_sec_rag_ingest.py tests/bronze/test_refresh_bronze_cot.py -q` (round-6 reproducer) → **116 passed, 7 skipped, 0 failed**
- `python3 -m pytest tests/rag/test_sec_rag_ingest.py::TestSparkCikMappingLogWriterSchema -q` → **4 passed** (real pyspark.sql.types path exercised)
- `git diff 0f4cb1c..HEAD -- tests` → no test deleted/weakened (see item 5)
- `grep -c 'ambiguous' pipelines/sec_rag_ingest.py` → 0
- leakcheck plugin (`-p leakcheck_plugin` after `test_sec_rag_ingest.py test_zz_isolation.py`) → 0 MagicMock pyspark keys; `databricks.connect == None`
===VERDICT END===
