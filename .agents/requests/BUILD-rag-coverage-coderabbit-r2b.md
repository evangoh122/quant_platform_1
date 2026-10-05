# BUILD: rag-coverage — tests for the CodeRabbit PR #28 round 2 fixes

You are MiMo. Branch `slice/rag-coverage` (stay on it). LF endings, never touch `.agents/dispatch.sh`, no Databricks, no network.
Run WSL commands directly (`wsl -d Ubuntu -- bash -lc '<cmd>'`); never wrap wsl.exe in PowerShell and never write scripts to C:\temp.
Your previous commit (the one before this request) fixed 8 CodeRabbit findings (`.agents/coderabbit-pr28-round2.md`) but added no test that
fails without each fix. COMMIT when done and update `.agents/mimo/VERDICT-rag-coverage-coderabbit-r2.md`.
For EACH of these, add a focused test that FAILS when the fix is reverted (show the red output for each in the verdict — revert in a
`git archive HEAD | tar -x -C /tmp/<dir>` copy, never in the worktree):
1. sec_rag_ingest single-accession lookup: the per-filing ownership check calls `read_existing_accession(..., accession)` (parameterized) and
   never `read_existing_accessions` (full table) — fake reader counting calls.
2. source CIK per filing: a filing discovered under CIK A is planned/fetched with CIK A even when the override group's iteration order differs.
3. reload_corpus resets `_alias_map_loaded` (after reload, the alias map is re-read).
4. invalidation resolves the alias first (reload_corpus("GOOGL") evicts the GOOG cache entry).
5. hybrid_retriever:191 per-ticker embedding fetch uses the same model resolution as vector_search (provider-aware).
6. evals/rag_eval/corpus.py offline alias map: the offline eval path never calls Spark/warehouse for alias lookups.
For api/main.py:305 (you judged "not valid"): explain in the verdict with file:line why the warm-up is already correct.
Acceptance: `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` green.
