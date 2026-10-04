# VERDICT: rag-ci-nopyspark — MiMo
**Status:** APPROVED
**Round:** 1

## Blocking findings
(none)

## What was fixed

CI runners have no `pyspark`. Eight tests that exercise code paths importing
`pyspark.sql.functions` (lazy imports inside `_load_corpus`, `build`, and the
`search_sec_filings` fallback) failed with `ImportError`.

**Root cause:** Production code uses lazy `from pyspark.sql import functions as F`
inside function bodies. Locally, databricks-connect provides pyspark; CI has
nothing. The existing test mocks (`MagicMock` for Spark sessions) assumed the
import itself would succeed.

**Fix:** Tests only. No production code changed.

| File | Change |
|------|--------|
| `tests/rag/conftest.py` | Added `fake_pyspark` fixture — installs stub `pyspark`, `pyspark.sql`, `pyspark.sql.functions`, `pyspark.sql.types` modules via `monkeypatch.setitem(sys.modules, ...)`. Column-expression helpers (`col`, `lit`, `lower`, `unix_timestamp`, `desc`) return a lightweight `_ColExpr` object supporting comparison operators (`<=`, `>=`, etc.) needed by chained Spark expressions. Also stubs `SparkSession` and `DataFrame` for `db.delta_adapter` import. |
| `tests/rag/test_hybrid_retriever.py` | Added `fake_pyspark` fixture parameter to the 8 failing tests: 4 in `TestEmbeddingBuildIdempotency`, 1 in `TestAcceptedEpochTimezoneSafe`, 3 in `TestSearchSecFilingsError`. |

## Non-blocking notes
- `_ColExpr` is a plain class (not MagicMock subclass) because MagicMock's metaclass `MagicMeta` installs `MagicProxy` descriptors for dunder methods that shadow class-level overrides.
- The fixture is function-scoped (via `monkeypatch`), so stubs are installed per-test and auto-cleaned. Zero impact on tests that don't request it.

## Mutation check

Removed the `as_of` filter from the fallback path in a /tmp copy of
`agent/tools_retrieval.py` (lines 138-144). Ran the PIT guard test under
`PYTHONPATH=/tmp/nopyspark`:

```
FAILED tests/rag/test_hybrid_retriever.py::TestSearchSecFilingsError::test_fallback_as_of_filters_future_filings
E   AssertionError: Expected at least 2 where calls (ticker + as_of), got 1
E   assert 1 >= 2
E    +  where 1 = len([<..._ColExpr object at 0x70d0ff29a990>])
```

Test correctly fails when as_of filter is removed — proves the guard is
load-bearing under the no-pyspark stub path.

## Checks run
- `PYTHONPATH=/tmp/nopyspark python3 -m pytest -q tests/rag/test_hybrid_retriever.py` → 59 passed
- `python3 -m pytest -q tests/rag/test_hybrid_retriever.py` → 59 passed (real pyspark)
- `PYTHONPATH=/tmp/nopyspark python3 -m pytest -q tests/rag` → 264 passed, 19 skipped
- `python3 -m pytest -q tests/rag` → 264 passed, 19 skipped (real pyspark)
- Mutation check (as_of removed) → 1 FAILED as expected