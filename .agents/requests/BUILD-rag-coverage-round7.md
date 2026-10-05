# BUILD rag-coverage round 7 (builder: MiMo) — one small isolation fix

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/rag-coverage. Descriptive commits.
NEVER delete or weaken existing tests. DeepSeek verdict: .agents/deepseek/VERDICT-rag-coverage-round6.md (items 1–3 PASS).

1 (blocking). tests/rag/test_sec_rag_ingest.py:26-27 does module-level `sys.modules.setdefault("databricks", MagicMock())` and
   `sys.modules.setdefault("databricks.connect", MagicMock())` at import time. That pollutes sys.modules for the whole pytest
   process; the session `spark` fixture in tests/bronze/test_refresh_bronze_cot.py:43-66 then gets a MagicMock session and 6 COT
   tests fail when suites run together. Reproducer: `python -m pytest tests/rag/test_sec_rag_ingest.py tests/bronze/test_refresh_bronze_cot.py -q`.
   Fix: remove the module-level setdefault; install the fakes with a fixture (monkeypatch.setitem(sys.modules, ...)) scoped to
   the tests that need them, so they are removed on teardown. Also make the COT `spark` fixture refuse a MagicMock/non-SparkSession
   (pytest.skip with a clear reason) as defense in depth. Check tests/rag for any other module-level sys.modules mutation and fix
   the same way.
   Test: a guard test that runs after the rag tests (e.g. in tests/rag/test_zz_isolation.py) asserting `"databricks.connect" not in
   sys.modules or not isinstance(sys.modules["databricks.connect"], MagicMock)`.
2. Correct item 4's root-cause note in your verdict (the "3 collection errors" claim was wrong; those files are skipped).
3. Minor (from ontology DeepSeek check): pipelines/sec_rag_ingest.py:385 comment `# mapped | missing | ambiguous` — the code never
   emits `ambiguous`; change the comment to `# mapped | missing`.
Acceptance: `python -m pytest tests/rag tests/bronze -q` (COMBINED) → 0 failed; the reproducer above → 0 failed; pyspark hidden
(PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps) tests/rag → 0 failed.
.agents/mimo/VERDICT-rag-coverage-round7.md with counts. Commit everything.
