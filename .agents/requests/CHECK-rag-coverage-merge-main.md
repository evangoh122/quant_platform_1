# CHECK: rag-coverage — merge of origin/main + Apps warehouse fallback + repair nits (checker: DeepSeek)

Read-only; mutations only in `git archive HEAD | tar -x -C /tmp/<dir>` copies; never run git inside a copy. Write
.agents/deepseek/VERDICT-rag-coverage-merge-main.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or
"Status: CHANGES_REQUESTED", file:line.
Commits: 5c1d6c2 (merge origin/main; conflict in api/services/hybrid_retriever.py + README resolved), ff24521 (repair_cik_ownership:
DISTINCT per filing + filing_url rewrite), efa3446 (warehouse-fallback tests; TABLE_OR_VIEW_NOT_FOUND → NoCoverageError).
Specs: .agents/requests/BUILD-rag-coverage-merge-main.md and -r2.md. MiMo verdicts are self-reports.
Claude: offline suite 2434 passed, 1 failed (tests/ml/test_hardening.py fold-local test — passes alone; branch does not touch ml/);
live (WSL, Spark forced off): `_fetch_ticker_rows("NVDA")` → 894 chunks / 894 embeddings via the SQL warehouse; gold_sec_coverage does not exist yet.
1. Merge correctness: nothing from main's #37 lost — compare main's hybrid_retriever behaviour (Spark-then-warehouse, `_get_spark` semantics,
   startup warm-up span `startup_sec_corpus_warm`) with the merged file; tests/api + tests/agent from main still pass.
2. Every Spark read in hybrid_retriever has a warehouse fallback with the ticker bound as a parameter (grep for f-string user values).
   Mutations: remove the ImportError fallback in `_fetch_ticker_rows` → a test fails; f-string the ticker into the coverage SQL → a test fails;
   remove the TABLE_OR_VIEW_NOT_FOUND conversion → a test fails.
3. Repair: DISTINCT gives one UPDATE per filing; filing_url rewrite is parameterized and only swaps the CIK path segment. Mutation: drop
   DISTINCT → a test fails.
4. Run `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` and report.
