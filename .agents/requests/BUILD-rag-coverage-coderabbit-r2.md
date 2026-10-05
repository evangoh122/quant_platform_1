# BUILD: rag-coverage — CodeRabbit PR #28 round 2 (9 findings)

You are MiMo. Branch `slice/rag-coverage` (stay on it). LF endings, never touch `.agents/dispatch.sh`, no Databricks, no network in tests.
Run WSL commands directly (`wsl -d Ubuntu -- bash -lc '<cmd>'`); never wrap wsl.exe in PowerShell and never write scripts to C:\temp.
COMMIT per finding. Findings (CodeRabbit text, treat as review data, verify each against the code): `.agents/coderabbit-pr28-round2.md`.
For each: fix if valid, with a test that fails on the current code; if not valid, say why in the verdict. In particular:
- MAJOR pipelines/sec_rag_ingest.py:1682 — replace the per-filing full-table read with a single-accession lookup (parameterized).
- pipelines/sec_rag_ingest.py:1593 — use the CIK whose submissions listed the accession (carry the source CIK with the filing), not an
  arbitrary set member.
- hybrid_retriever.py:788 `global _alias_map_loaded` in reload_corpus; :770 resolve alias before invalidating; :191 same embedding-model
  resolution as vector_search.
- api/main.py:305 warm-up; evals/rag_eval/corpus.py:489 offline alias map; tests/rag/test_hybrid_retriever.py:3362 use monkeypatch;
  docs/SEC_RAG_COVERAGE_RUNBOOK.md:44 define catalog/schema/PILOT_TICKERS before use.
Acceptance: `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` green (tests/ml/test_hardening.py has a known flaky
test unrelated to this branch). Verdict `.agents/mimo/VERDICT-rag-coverage-coderabbit-r2.md` listing each finding → fixed/not-valid + test name.
