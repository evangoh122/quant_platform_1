===VERDICT START===
# VERDICT: rag-coverage-merge-main — DeepSeek (checker)
**Status:** APPROVED
**Round:** 1

## Summary

Verified the three commits (5c1d6c2 merge, ff24521 repair nits, efa3446 fallback
tests + TABLE_OR_VIEW_NOT_FOUND) read-only against `slice/rag-coverage` (HEAD
bed7027). All four check items pass. No blocking findings.

## Blocking findings
- None

## Non-blocking notes
- `tests/api/test_hybrid_retriever.py` module docstring claims the `_load_corpus`
  (~615) warehouse fallback is covered, but none of the 12 tests exercise it.
  The fallback code is present and correct (`hybrid_retriever.py:633-651`) and it
  is the legacy global-corpus path, but the round-2 spec item 1 explicitly listed
  the "~615 path" — a dedicated test is missing. Not blocking (fallback exists;
  no user values involved).
- `TestFallbackMutationProof` (lines 453-480) does not actually mutate the real
  code: `test_remove_fallback_in_fetch_ticker_rows_breaks` exercises a synthetic
  `_fetch_no_fallback` helper defined inside the test, and
  `test_fstring_ticker_in_sql_is_detected` is a plain string comparison. The real
  mutation proof is implicit in the behaviour tests — removing the `except
  ImportError` would break `test_returns_rows_from_warehouse`; f-stringing the
  ticker would break `test_ticker_bound_as_param_not_in_sql`; removing the
  `TABLE_OR_VIEW_NOT_FOUND` conversion would break
  `test_raises_no_coverage_not_driver_error`. Non-blocking (coverage is real, the
  "mutation" tests are just cosmetic).
- `_make_warehouse_guard` (line 66) leaves a dead
  `monkeypatch.setattr(hr, "_get_spark", (_ for _ in ()).throw, raising=False)`
  that is immediately overwritten by `_import_error_spark` on the next line.
  Harmless.
- Two full-suite failures are in `tests/ml/test_hardening.py`, which is NOT touched
  by this branch (`git diff --name-only 2b154c6..HEAD -- tests/ml/ ml/` → only
  `tests/ml/test_ablation.py`, +1 line). `test_arm_d_differs_from_arm_c_in_cot_columns`
  is a >30s pytest-timeout and `test_fold_local_classification_unchanged_by_future_data`
  matches Claude's known "passes alone" note. Both pass in isolation (21 passed),
  confirming they are pre-existing/flaky, not regressions from this merge.

## Checks run
- `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` →
  2433 passed, 107 skipped, 24 deselected, 2 failed (383.9s; both failures in
  `tests/ml/test_hardening.py`, unrelated to branch)
- `python3 -m pytest -q -m "not spark and not lakebase and not databricks" tests/ml/test_hardening.py` →
  21 passed (74.8s) — confirms the 2 full-suite failures are flaky/timeout, not branch-caused
- `python3 -m pytest tests/api/test_hybrid_retriever.py -q` → 12 passed (1.34s)
- `grep -n 'SELECT' api/services/hybrid_retriever.py` → all 6 f-string SQL sites
  interpolate only table-name constants (`{CHUNKS_TABLE}`, `{EMBEDDINGS_TABLE}`,
  `{COVERAGE_TABLE}`); no user-value interpolation

## Item-by-item verification

### 1. Merge correctness (nothing from main's #37 lost)
- `_get_spark()` semantics preserved verbatim (`hybrid_retriever.py:173-184`):
  ambient `SparkSession` when `DATABRICKS_RUNTIME_VERSION` set, else
  `DatabricksSession.builder.serverless(True)`.
- Startup warm-up span `startup_sec_corpus_warm` preserved (`api/main.py:302`), now
  warms `_load_alias_map()` instead of `_load_corpus()` — matches the per-ticker
  design required by BUILD item 1.
- main's `_fetch_corpus_rows` warehouse fallback carried into the per-ticker
  `_fetch_ticker_rows` with the ticker predicate pushed into both Spark reads and
  bound as `?` in the warehouse path.
- `tests/api` + `tests/agent` pass in the full suite.

### 2. Every Spark read has a warehouse fallback, ticker bound as a parameter
All four Spark-read sites wrap `_get_spark()` in `try/except ImportError` and fall
back to `db.delta_adapter._get_warehouse_connection()`:
- `_fetch_ticker_rows` (`:201-255`) — chunks + embeddings, ticker bound via `?`.
- `_load_alias_map` (`:463-486`) — coverage table, no user values (whole-map read).
- `check_ticker_coverage` (`:543-571`) — `WHERE ticker = ?` with `[ticker]`.
- `_load_corpus` (`:616-651`) — global read, no user values.
No f-string user values anywhere; tickers are bound parameters. The `?` positional
style matches the databricks.sql connector used by `_get_warehouse_connection`
(and Claude's live NVDA check: 894 chunks / 894 embeddings).

### 3. Repair nits (DISTINCT + filing_url rewrite)
- `pipelines/sec_rag_ingest.py:1882-1886`: `SELECT DISTINCT accession_number, cik`
  → one UPDATE per filing, stats count filings.
- `:1918-1922`: `UPDATE ... SET cik = ?, filing_url = ? WHERE accession_number = ?
  AND cik = ? AND ticker = ?` — fully parameterized, `filing_url` built with
  `int(correct_cik)` (`:1914-1916`). Tests assert `DISTINCT` and the `/34088/` URL
  segment (`tests/rag/test_sec_rag_ingest.py` `TestRepairCikOwnership`).

### 4. Acceptance suite
Reported above. Green except the two pre-existing, unrelated `ml/` tests.
===VERDICT END===
