# BUILD-rag-coverage round 16b — FINISH the in-progress merge of origin/main — IMPLEMENT NOW

You are MiMo. A merge of origin/main is IN PROGRESS in this worktree (MERGE_HEAD present, markers already removed, NOT committed).
Do NOT abort it, do NOT start a new merge. Fix and then COMMIT it (`git commit --no-edit`), then write the verdict. LF endings, do not touch
`.agents/dispatch.sh`. Commit early — you timed out last time before committing.

Claude ran the merged tree in WSL: `pytest tests/rag tests/bronze` → 19 failed, 1106 passed. 18 are rag_eval tests from main (#26) because
your resolution of `agent/tools_retrieval.py::search_sec_filings` DELETED main's substring-fallback (the generic `except Exception` branch that
queries silver_sec_sections with the PIT `accepted_ts <= as_of` filter, `retrieval_mode="substring_fallback"`, `chunk_id`, `_warning`).
"Keep both sides" means: keep this branch's `except (NoCoverageError, TickerRequiredError)` → no_coverage / ticker_required responses AND
main's `retrieve_and_rerank` call AND main's generic-exception substring fallback exactly as on origin/main (`git show origin/main:agent/tools_retrieval.py`).
NoCoverage must NOT fall through to the substring fallback (a ticker with no coverage returns no_coverage, not substring hits).
Also fix `tests/rag/test_zz_isolation.py::test_databricks_connect_not_polluted` (find which merged test/fixture leaves databricks.connect polluted).
Acceptance (report counts): `python3 -m pytest tests/rag tests/bronze -q` → 0 failed (the 5 test_merge_metrics `databricks.connect` errors you saw
on Windows are environment-only; note them, they pass in WSL). Verdict: .agents/mimo/VERDICT-rag-coverage-round16-merge.md listing per conflicted
file what each side contributed and how you resolved it.
