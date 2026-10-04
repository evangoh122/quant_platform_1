# BUILD: SEC knowledge graph round 5, tests only (MiMo)

> **IMPLEMENT NOW.** No confirmation questions. Commit when done. Don't change production code
> unless a test reveals a real bug.

Checker (`.agents/deepseek/VERDICT-rag-kg-check4.md`): the production timestamp fix is CORRECT. Two
test issues:
1. **[Blocking]** `_patch_pyspark` (`tests/rag/test_sec_knowledge_graph.py:~1536`) imports the REAL
   `pyspark.sql.functions`, so 4 `TestSparkGraphStoreRoundTrip` tests fail with pyspark hidden. CI has
   no pyspark. Register a fake `pyspark` / `pyspark.sql` / `pyspark.sql.functions` module tree with
   `monkeypatch.setitem(sys.modules, ...)` (like the `fake_pyspark` fixture in `tests/rag/conftest.py`).
   Prove the tests pass with pyspark hidden, using a sitecustomize that sets
   `sys.modules[m]=None` for pyspark*.
2. **`test_neighbors_returns_utc_timestamps` is vacuous.** It queries `["FILED"]`, which returns `[]`.
   Query `["REPORTED_FACT"]` and assert a NON-EMPTY result with the correct UTC timestamps.

Run `python3 -m pytest -q -p no:cacheprovider tests/rag`, and the full suite with
`--ignore=tests/lakebase`, both with and without pyspark hidden. LF line endings only. Don't touch
`.agents/dispatch.sh`. Write `.agents/mimo/VERDICT-rag-kg-round5.md`.
