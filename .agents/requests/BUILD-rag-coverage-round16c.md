# BUILD-rag-coverage round 16c — IMPLEMENT NOW (post-merge test fixes; small)

You are MiMo. The merge is committed (5ba57e4) and keeps both sides. Claude in WSL: `pytest tests/rag tests/bronze` → 2 failed, 1123 passed.
Commit as you go, LF endings, do not touch `.agents/dispatch.sh`, never weaken a test's intent.
1. tests/rag/test_hybrid_retriever.py::TestSearchSecFilingsError::test_generic_exception_returns_retrieval_unavailable — after restoring main's
   substring fallback, a generic hybrid failure now runs the fallback, which tries a REAL Databricks Spark connection (network-blocked in tests →
   "connection timeout"). Update the test to the merged contract: mock the fallback's `_spark()` to raise → `retrieval_unavailable`; add a sibling
   test where the fallback succeeds (fake Spark table) → `retrieval_mode == "substring_fallback"`, PIT filter applied; and assert NoCoverageError
   never reaches the fallback (returns no_coverage). No test may touch the network.
2. tests/rag/test_zz_isolation.py::test_databricks_connect_not_polluted — passes alone, fails in the suite: find the test/fixture that imports or
   patches `databricks.connect` without restoring it (bisect with `pytest tests/rag -p no:randomly --co` order + `-x`) and fix the leak there
   (fixture teardown / monkeypatch), not in the isolation test.
Acceptance: `python3 -m pytest tests/rag tests/bronze -q` → 0 failed. Verdict: .agents/mimo/VERDICT-rag-coverage-round16c.md.
