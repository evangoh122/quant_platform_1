# BUILD: rag-coverage merge-main round 2 — the missing fallback tests (+ missing-coverage-table behaviour)

You are MiMo. Branch `slice/rag-coverage` (stay on it). LF endings, never touch `.agents/dispatch.sh`, no Databricks. COMMIT your work.
Round 1 (5c1d6c2 merge, ff24521) added the Spark-then-warehouse fallback in api/services/hybrid_retriever.py (`_fetch_ticker_rows` ~194,
`_load_alias_map` ~464, `check_ticker_coverage` ~545, ~615) but NO tests for it, which BUILD-rag-coverage-merge-main.md item 1 required.
Claude live check: the warehouse path works for NVDA (894 chunks / 894 embeddings); `gold_sec_coverage` does not exist yet in the workspace.

1. Tests (tests/api/test_hybrid_retriever.py or a new file): patch `_get_spark` to raise ImportError and patch
   `db.delta_adapter._get_warehouse_connection` with a fake connection/cursor that records (sql, params). Assert for `_fetch_ticker_rows("NVDA")`,
   `check_ticker_coverage("NVDA")`, `_load_alias_map()` and the ~615 path: rows are returned/mapped correctly, the ticker is passed in
   `params` (not in the SQL text), and no "NVDA" literal appears in the SQL. Mutations (paste FAILED output): remove the `except ImportError`
   fallback in `_fetch_ticker_rows` → a test fails; f-string the ticker into the coverage SQL → a test fails.
2. Missing coverage table: if `gold_sec_coverage` is absent (warehouse raises TABLE_OR_VIEW_NOT_FOUND / Spark AnalysisException), the alias
   map degrades to an empty map with a WARNING log, and `check_ticker_coverage` raises the existing structured unavailable/no-coverage error
   (not a raw driver exception) so the API returns a clean error. The startup warm-up must not crash the app. Tests for both.
Acceptance: `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` green. Verdict `.agents/mimo/VERDICT-rag-coverage-merge-main-r2.md`.

## RESUME NOTE (Claude, after a PC restart killed round 2 mid-way)
A partial, uncommitted `tests/api/test_hybrid_retriever.py` (473 lines) from your interrupted run is in the worktree. Review it, finish
items 1 and 2, run the acceptance suite, and COMMIT.
