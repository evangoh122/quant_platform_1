# BUILD-rag-coverage round 16 — MERGE origin/main — IMPLEMENT NOW

You are MiMo. The branch is fully approved (DeepSeek r15, Codex r6, Claude final review + live AAPL ingest: 8 filings, 469 rows,
idempotent rerun 0 rows). Before the PR, merge `origin/main` (now includes #16 residual reversion, #26 rag-kg, #27 nl-contracts).
`git fetch origin && git merge origin/main` → conflicts in: agent/tools_retrieval.py, docs/DATA_SCHEMAS.md, pipelines/run_silver_gold.py,
resources/jobs.yml, tests/rag/conftest.py, tests/rag/test_hybrid_retriever.py.

Rules: keep BOTH sides' behaviour. This branch's must-keep: SEC coverage pipeline (gold_sec_coverage, NoCoverageError/no_coverage
responses), sec_rag_ingest + embeddings jobs with user-agent secret params, rows=unknown semantics, prod catalog rendering. Main's
must-keep: everything from #16/#26/#27 (adjusted prices, KG/ontology, NL contracts, silver/gold refresh changes, test fixtures).
For resources/jobs.yml keep every job from both sides. Remove ALL conflict markers (grep `^(<<<<<<<|=======|>>>>>>>)` over the tree must
return nothing). Commit the merge (one merge commit, LF endings), do not touch `.agents/dispatch.sh`.
Run: python3 -m pytest tests/rag tests/bronze -q AND python3 -m pytest -q -m "not spark and not lakebase and not databricks"
(report counts; known ml ablation timeout excepted). Write .agents/mimo/VERDICT-rag-coverage-round16-merge.md listing, per conflicted
file, what each side contributed and how you resolved it.
