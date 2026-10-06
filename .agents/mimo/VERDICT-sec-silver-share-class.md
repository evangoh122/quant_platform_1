# VERDICT: sec-silver-share-class — MiMo
**Status:** APPROVED
**Round:** 1

## Summary

Fixed the canonical-ticker selection in two locations so that share-class aliases
(e.g. GOOG/GOOGL) resolve to whichever ticker actually holds the silver SEC chunks,
not just the alphabetically-first ticker.

## Changes

### 1. `gold/07_gold_sec_coverage.sql` — canonical_per_cik CTE
- **Before:** `min(ticker)` → picks GOOG (alphabetically first, 0 chunks)
- **After:** `QUALIFY ROW_NUMBER() OVER (PARTITION BY cik ORDER BY coalesce(n_chunks, 0) DESC, ticker ASC) = 1`
- Added `ticker_chunk_counts` CTE joining `silver_sec_sections` chunk counts into `latest_mapping`
- Both GOOG and GOOGL rows now resolve to GOOGL canonical with n_chunks = 831

### 2. `api/services/hybrid_retriever.py` — `_load_alias_map()`
- **Before:** `sorted(tickers)[0]` → picks GOOG (alphabetically first)
- **After:** `SELECT ticker, cik, n_chunks FROM gold_sec_coverage` then sort by `(-n_chunks, ticker)`
- Both GOOG and GOOGL map to GOOGL canonical

### 3. Tests
- `tests/gold/test_gold_sec_coverage_sql.py` — DuckDB SQL semantics test:
  - CIK 0001652044: GOOG(0)/GOOGL(831) → canonical GOOGL, both rows report 831
  - CIK 0001045810: NVDA single-ticker → unchanged
  - Mutation proof: `min(ticker)` → picks GOOG (wrong, 0 chunks) → FAILS
- `tests/api/test_hybrid_retriever.py` — alias map tests:
  - Fake coverage rows with n_chunks; canonical = max(n_chunks)
  - Alphabetical tie-break when n_chunks equal
  - Mutation proof: `sorted()[0]` → picks zero-chunk ticker → FAILS

## Blocking findings
- None.

## Non-blocking notes
- The `QUALIFY` syntax in `07_gold_sec_coverage.sql` is Databricks-native. DuckDB also supports it (verified in tests). If migrating to a dialect without QUALIFY, use a subquery + WHERE rn = 1 pattern.
- The `ticker_chunk_counts` CTE in the SQL duplicates the existing `chunk_agg` CTE (lines 86-91). They compute the same thing. A future refactor could deduplicate, but both are needed at different points in the CTE chain (canonical selection vs. final SELECT join).

## Checks run
- `python -m pytest tests/gold/test_gold_sec_coverage_sql.py -v` → 4 passed
- `python -m pytest tests/api/test_hybrid_retriever.py::TestLoadAliasMapWarehouse -v` → 3 passed
- `python -m pytest tests/gold/test_gold_sec_coverage_sql.py tests/api/test_hybrid_retriever.py::TestLoadAliasMapWarehouse -v` → 7 passed

## Commits
- `e0defee` fix(gold): canonical ticker = max(n_chunks) then alphabetical in 07_gold_sec_coverage
- `6584cb3` fix(api): alias map picks canonical by max(n_chunks) not alphabetical
- `635c321` test: canonical-ticker semantics for 07_gold_sec_coverage and alias map