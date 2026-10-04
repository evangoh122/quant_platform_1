# VERDICT: rag-coverage-round17-ci — MiMo
**Status:** APPROVED
**Round:** 17

## Blocking findings
None.

## Non-blocking notes
- The `_install_pyspark_stubs` fixture had a `try/except ImportError: pass` that left `pyspark.sql.types` empty when real pyspark was absent. `sec_rag_ingest.py` does lazy `from pyspark.sql.types import IntegerType, ...` inside `_ensure_schema()`, which then failed with `ImportError: cannot import name 'IntegerType'`.
- Fix: added fallback `_StubType` base class and generated stub subclasses for all 7 pyspark types (BooleanType, IntegerType, LongType, StringType, TimestampType, StructField, StructType) when real types are unavailable. These are callable stand-ins sufficient for schema construction; real types are still preferred when pyspark is installed.
- The 3 collection errors in `tests/rag/test_chat_engine.py`, `test_graph_rag_engine.py`, `test_langgraph_engine.py` are pre-existing (missing `api.db` module) and unrelated to this change.

## Checks run
- `python -m pytest tests/rag/test_merge_metrics.py -q` (no pyspark) → 12 passed
- `python -m pytest tests/rag/test_merge_metrics.py -q` (with pyspark) → 12 passed
- `python -m pytest tests/rag tests/bronze -q` (no pyspark) → 12 passed in test_merge_metrics, 3 pre-existing collection errors in other files (unrelated)

## Commit
- `d10b819` on `slice/rag-coverage` — `fix(tests): add fallback pyspark type stubs for no-pyspark CI`