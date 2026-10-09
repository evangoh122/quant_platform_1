# VERDICT: decision-p0a — DeepSeek
**Status:** CHANGES_REQUESTED
**Round:** 1

## Blocking findings
- [db/delta_adapter.py:457] The **market-features PySpark read** still applies `.limit(limit)` with no `orderBy`, so daily bars are returned in nondeterministic (non-newest-first) order. `agent/tools_retrieval.get_market_features` (agent/tools_retrieval.py:87-92) delegates to this read, and Fix 1's mandate ("check the market-features Spark read for the same defect") is therefore not satisfied. The warehouse fallback `_build_market_features_daily_query` (db/delta_adapter.py:69) orders `event_date DESC`, so the two backends now disagree on row order. Fix: add `.orderBy(F.col("event_date").desc())` before `.limit(limit)` in the pyspark branch, matching the warehouse query. Note the options read (`get_options_features`) was fixed correctly; only the sibling market-features read was missed.

## Non-blocking notes
- `.agents/run-mutations.py` runs every mutation with `--noconftest`, which disables `tests/api/conftest.py`. I confirmed that `test_start_time_matches_helper_output` and `test_null_pnl_serializes_as_json_null` then error with `fixture 'fake_lakebase' not found` even on unmutated code, so M2/M3 in MiMo's own transcript would "fail" for the wrong reason. My independent re-run (isolated `git archive` copies, **without** `--noconftest`) confirms all five mutations genuinely fail for the intended reason (M1 `ValueError: 'orderBy' not in list`; M2 start_time assertion; M3 `AssertionError` null != 0.0; M5 weekday assertion). The underlying claim holds despite the tooling flaw.
- M4 (remove count guard) is killed by a duckdb `ParserException`, not the intended "early rows NULL" assertion: `_extract_zscore_expression` walks backward and, once the `CASE` is gone, grabs a large SQL span (from an unrelated `CASE` in the `oi_conc` CTE), producing malformed SQL. The behavioral test is valid on correct code (it executes the real production expression against duckdb) and `test_gold_sql_contains_count_guard` independently regex-checks the guard, but the mutation-kill reason is not the semantic one.
- `api/trading_days.py` docstring claims the count is "inclusive of `end`"; the loop actually counts weekdays strictly before `end` (verified: `start_for_trading_days(Wed, 5)` = prior Wednesday, i.e. 5 weekdays back). No functional impact for the ~1-year default; docstring imprecision only.
- Frontend totals (PaperPortfolio.tsx) drop a position from totals only when both `realized_pnl` and `unrealized_pnl` are non-null; a partially-null position (one field null) is excluded wholesale. The vitest only exercises the both-null vs both-present cases. Acceptable for the realistic both-null case; edge case not handled/tested.
- `get_cot_positioning` (agent/tools_retrieval.py:442) also does `.limit(1)` without `orderBy` — same defect class, but COT is outside the "market features" scope; recommend a follow-up.

## Checks run
- `git rev-parse HEAD` → `aacee9c6fd72ab8f0667be8854790f6da6e302d3` (matches request) → pass
- `git status --porcelain --untracked-files=no` → clean tracked tree → pass
- `git merge-base --is-ancestor origin/main HEAD` → pass (merge-base `45f6979` = origin/main)
- `git diff --check origin/main...HEAD` → pass
- Scope audit (`git diff --stat origin/main...HEAD`, both commits): exactly the 4 fixes + tests + evidence; no dependency-file changes (duckdb already present at requirements.txt:27) → pass
- `.agents/run-decision-p0a-check.sh` via `wsl.exe -d Ubuntu -- bash /home/jianj/code/qp1-decision-p0/.agents/run-decision-p0a-check.sh` → pass (485 pytest; 16 files / 246 vitest; `npx tsc --noEmit`; `npm run build`)
- Independent mutation re-run (isolated `git archive` copies, no `--noconftest`): M1 PASS, M2 PASS, M3 PASS, M4 PASS (parser-error kill), M5 PASS → all mutations detected

VALIDATION DONE | verdict: CHANGES_REQUESTED | sha: aacee9c6fd72ab8f0667be8854790f6da6e302d3 | evidence: .agents/deepseek/VERDICT-decision-p0a.md
