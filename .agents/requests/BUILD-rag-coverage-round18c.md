# BUILD-rag-coverage round 18c — IMPLEMENT NOW (round-18 alias resolution hangs the test suite and adds Spark calls per query)

You are MiMo. Stay on branch `slice/rag-coverage` (do not create/switch branches). Commit per item, LF endings, do not touch `.agents/dispatch.sh`,
never weaken tests, paste each mutation's FAILED output into the verdict.
State: Claude committed af75e69 (autouse XBRL HTTP + User-Agent stub in tests/rag/conftest.py; fixes the sec.gov calls from round 18 #7).
Remaining hang (Claude, WSL, `pytest tests/rag tests/bronze -x --timeout 10`):
`tests/rag/test_hybrid_retriever.py::TestBM25DenseFusion::test_bm25_returns_relevant_docs` → bm25_search (hybrid_retriever.py:830) →
get_ticker_corpus (:332) → `_resolve_canonical_ticker` (:397-425, round-18 fix #2) → `_get_spark()` (:180) → a REAL Databricks Connect session →
network timeout. Every test that loads a corpus now hangs; the full suite never finishes.
1. Design: alias resolution must not issue two extra Spark queries on every retrieval. Load the (ticker → canonical ticker) alias map ONCE with the
   coverage data (same place/cached the way check_ticker_coverage loads coverage), cache it, and resolve from the map; fall back to the ticker itself
   when the map is unavailable, logging once. Coverage lookup and alias lookup should share one cached read.
2. Tests: the existing corpus fixtures must not touch Spark — inject the alias map (or the coverage loader) via the same seam the tests already use for
   coverage; add a guard in tests/rag/conftest.py that makes `_get_spark` raise immediately in tests unless a test explicitly patches it, plus a
   socket/DNS guard (like tests/strategies/conftest.py) so any future network call fails fast instead of hanging. Keep the alias tests from round 18
   (GOOGL → GOOG chunks labelled with the requested ticker) passing through the cached map. Mutation: drop alias resolution → alias test FAILS.
Acceptance: `python3 -m pytest tests/rag tests/bronze -q --timeout 60` FINISHES in < 3 min and passes in Claude's WSL (pyspark + Databricks auth
present) and without pyspark (CI). Verdict: .agents/mimo/VERDICT-rag-coverage-round18c.md.
