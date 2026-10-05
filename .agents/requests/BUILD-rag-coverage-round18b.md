# BUILD-rag-coverage round 18b — IMPLEMENT NOW (round 18 made tests hit the real SEC API → suite hangs)

You are MiMo. Stay on branch `slice/rag-coverage` (do not create/switch branches). Commit, LF endings, do not touch `.agents/dispatch.sh`.
After round 18 (fix #7: XBRL client reuses the pipeline User-Agent resolver), `python3 -m pytest tests/rag tests/bronze` no longer finishes in
WSL: tests/rag/test_eval_pipeline.py::TestConfidenceScorer::test_amended_filing_trigger (and others) now make REAL HTTP calls to sec.gov —
api/services/confidence_scorer.py:178 → xbrl_cross_validator.py:66 cross_validate → xbrl_client.py:86 get_fact → :69 fetch_company_facts →
:51 _rate_limited_get → urllib3 connect timeout. Previously the missing EDGAR_USER_AGENT made the client return {} immediately; now the resolver
finds the real env/secret and the call goes out (and can even read the workspace secret during tests).
Fix:
1. Tests must never reach the network or the Databricks secret: add an autouse fixture in tests/rag/conftest.py (and tests/api if needed) that
   (a) stubs the XBRL HTTP layer (`xbrl_client._rate_limited_get` / `fetch_company_facts`) to return canned facts or {} and (b) prevents the
   User-Agent resolver from calling the Databricks SDK (monkeypatch the resolver or set a fixture env value); plus a socket/DNS guard
   (like tests/strategies/conftest.py) that fails fast with a clear message on any real connection.
2. Tests that exercise XBRL cross-validation use explicit canned facts (keep their assertions meaningful).
3. Acceptance: `python3 -m pytest tests/rag tests/bronze -q --timeout 60` finishes (< 3 min) and passes in an environment where
   SEC_EDGAR_USER_AGENT IS set and Databricks auth IS available (Claude's WSL) — and also without pyspark (CI).
Verdict: .agents/mimo/VERDICT-rag-coverage-round18b.md.
