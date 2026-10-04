# BUILD rag-coverage round 8c (builder: MiMo) — make four tests load-bearing

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/rag-coverage. Descriptive commits. NEVER delete or weaken tests.
DeepSeek verdict: .agents/deepseek/VERDICT-rag-coverage-round8b.md (production fixes verified; 4 tests don't detect regressions).
RULE: each test must FAIL under the named mutation; prove it in a copy made with `git archive HEAD | tar -x -C /tmp/<dir>` and paste the output.

1. tests/rag/test_sec_embeddings_incremental.py:368 — inspect the actual predicate: build a tiny DataFrame stand-in (or capture the Column expression
   and evaluate it on rows) and assert a comma list "AAPL,MSFT" keeps AAPL and MSFT rows and drops others. Mutation: scalar `F.col("ticker") == ...`
   → FAILS.
2. :435 — embed a batch where candidates ≠ inserted (e.g. 3 candidates, MERGE metrics report numTargetRowsInserted = 1 because 2 already exist).
   Assert rows_written == 1. Mutation: `return len(out_rows)` → FAILS.
3. tests/rag/test_sec_coverage_sql.py — add a DuckDB test that extracts the SQL from gold/07_gold_sec_coverage.sql (placeholders substituted the same
   way the runner does; documented minimal shim only) and runs it on fixtures: universe, sec_cik_mapping_log (two entries for one ticker — older
   'missing', newer 'mapped'), filings, chunks, plus one out-of-universe ticker. Assert exact output rows (CIK from the latest mapped entry, mapped
   zero-filing ticker present with its CIK, out-of-universe excluded). Mutations: flip ROW_NUMBER ORDER BY mapped_ts direction → FAILS; drop the
   universe restriction → FAILS.
4. :315 — also assert both concurrent batches' rows reached the target table.
Acceptance: python3 -m pytest tests/rag tests/bronze -q all pass; pyspark hidden (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps).
.agents/mimo/VERDICT-rag-coverage-round8c.md with mutation outputs. Commit everything.
