# BUILD: rag-coverage — merge origin/main and keep Databricks Apps retrieval working (+ 2 repair nits)

You are MiMo. Branch `slice/rag-coverage` (worktree qp1-ragcov; stay on it, no new branches). LF endings, never touch
`.agents/dispatch.sh`, no Databricks calls. COMMIT (a merge commit, then one commit per extra item).

## 1. `git merge origin/main` (run `git fetch origin` first). Conflicts: `api/services/hybrid_retriever.py`, `README.md`.
- main (PR #37, commits 56cd531 + 4ab760a) made SEC retrieval work INSIDE Databricks Apps, which have no Spark: `_fetch_corpus_rows()` tries
  `_get_spark()` and on `ImportError` falls back to the SQL warehouse via `db.delta_adapter._get_warehouse_connection()`; `_get_spark()`
  uses the ambient session when `DATABRICKS_RUNTIME_VERSION` is set, otherwise `DatabricksSession...serverless(True)`; the app warms the
  corpus in the background at startup (see api/main.py on main, trace span `startup_sec_corpus_warm`).
- This branch replaced the single corpus load with per-ticker loading (`_load_ticker_corpus`, `get_ticker_corpus`, `_load_alias_map`,
  `check_ticker_coverage`, `_load_corpus`, `reload_corpus(ticker)`), all Spark-only. Keep the branch's design and add the same
  Spark-then-warehouse fallback to EVERY Spark read in it: chunks + embeddings per ticker, the coverage table, the alias map. Warehouse SQL
  must bind the ticker as a parameter (no f-string user values; table names are constants). Keep main's `_get_spark()` semantics.
- Make the startup warm-up in api/main.py compatible with the per-ticker design (warm the alias map/coverage, not the whole corpus).
- README.md: keep main's text; update the SEC retrieval rows to say the universe-wide rollout is in this PR.
- Tests: with `_get_spark` raising ImportError and a fake warehouse connection, `get_ticker_corpus("NVDA")`, `check_ticker_coverage`,
  and `_load_alias_map` work and pass the ticker as a bound parameter. Mutation: remove the fallback in `_load_ticker_corpus` → a test fails.
  Keep all main tests (tests/api, tests/agent) and branch tests passing.

## 2. repair_cik_ownership nits (Claude live review): the SELECT iterates one row per CHUNK (live XOM: 21 identical UPDATEs for one filing)
- select DISTINCT accession_number, cik so there is one UPDATE per filing and stats count filings;
- also rewrite `filing_url` to `.../edgar/data/{int(correct_cik)}/...` in the same parameterized UPDATE. Tests for both.

Acceptance: `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` green. Verdict `.agents/mimo/VERDICT-rag-coverage-merge-main.md`.
