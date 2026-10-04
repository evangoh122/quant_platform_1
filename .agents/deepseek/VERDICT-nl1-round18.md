===VERDICT START===
# VERDICT: nl1-round18 — DeepSeek (checker)
**Status:** APPROVED
**Round:** 18

Range verified: `2c305bc` (MiMo round-18 build). Source read-only; every mutation performed in `/tmp/r18m*` copies created via `git archive HEAD | tar -x -C /tmp/<dir>`. Working tree untouched by this check.

Both round-17 blocking findings are now closed. The COALESCE(...,0) semantic change is reverted in production; the DuckDB-only eager `LN(0)` error is fixed in the `to_duckdb()` shim alone; and the adjusted-mode momentum LAG-before-null-filter mutation is now killed. Items 1–4 of the check request all pass.

## Item 1 — production DOC revert confirmed

`git diff 7275130^ HEAD -- docs/NL1_PROPOSED_SERVING_VIEWS.md` (round-16/pre-17 vs HEAD) shows exactly three changes, all confined to `serve_relative_performance_v1`:

- `COALESCE(return_1d, 0)` → `return_1d` (doc:433) and `COALESCE(bench_return, 0)` → `bench_return` (doc:460) — removed.
- `WHERE return_1d IS NOT NULL` / `WHERE bench_return IS NOT NULL` restored. They now live in the input CTEs (`entity_returns`:398, `benchmark_returns`:409) rather than at the bottom of `entity_cumulative`/`benchmark_cumulative` (round-16 :441/:466).
- The false comment ("treated as no-change (0%)… propagate through BOOL_OR") removed; replaced with an accurate note ("excluded upstream (WHERE IS NOT NULL)").

The filter relocation is **semantically equivalent**: a CTE's `WHERE` is applied to its input rows *before* the window functions in its SELECT list, so filtering in `entity_returns` vs at the bottom of `entity_cumulative` excludes the NULL day from `BOOL_OR`/`SUM`/`MAX` windows identically. Verified empirically in DuckDB: round-16 SQL and round-18 SQL produce **identical** output on (a) a masked-NULL day and (b) a −100% day — including `entity_info_ts`, using a late-revision fixture where the NULL day carries a later `information_available_ts` than the next valid day. No other production file changed (`git show 2c305bc --stat`: only the doc, plus test files).

## Item 2 — LN(0) guard is shim-only and documented

- Production DOC has plain `LN(1 + return_1d)` / `LN(1 + bench_return)` (doc:433, :460). No `COALESCE`, no `GREATEST` guard in production.
- `tests/analytics_nl/_ddl_extract.py:135-151` (`to_duckdb`) adds `LN(1 + col)` → `LN(GREATEST(1 + col, 1e-10))` (Pattern A) plus a legacy `COALESCE` Pattern B, with a comment stating it is a DuckDB evaluation-order workaround and that "production keeps its CASE/NULL semantics".
- Tests: `test_minus_100_percent_day_gives_null_and_invalid_return` (→ NULL cumulative + `invalid_return`) and `test_null_return_day_is_excluded` (masked NULL day excluded, not 0%) both pass.
- Mutation proof: re-adding the full round-17 state (`COALESCE` + removing `WHERE return_1d IS NOT NULL`) → `test_null_return_day_is_excluded` **FAILS** (`/tmp/r18m1`, 1 failed: NULL day reappears in output). Note: re-adding `COALESCE` *while keeping* the `WHERE IS NOT NULL` filter does **not** fail test (b) — correct, since the WHERE filter is what excludes the NULL day; the test guards against the real regression (COALESCE + dropped filter).

## Item 3 — adjusted-mode momentum mutation closed

`test_adjusted_momentum_lag_before_null_filter` (`test_ddl.py:1522`) inspects the **adjusted** variant's `with_momentum` CTE. Mutation: add `WHERE return_1d IS NOT NULL` to the adjusted `with_momentum` (`FROM returns_from_source`) → test **FAILS** (`/tmp/r18m2`, 1 failed). This closes the round-16/17 finding 3b/4a that previously survived (the round-17 test only checked the fallback variant).

## Item 4 — round-16/17 doc mutations all still killed

Re-run against production DOC in `git archive` copies:

| Mutation | Result |
|---|---|
| `THEN NULL` → `THEN -0.99` | 1 failed — caught |
| `WHEN e.has_invalid_return OR b.has_invalid_bench THEN 'invalid_return'` → `WHEN FALSE` | 1 failed — caught |
| drop `momentum_20d_info_ts` from final GREATEST | 1 failed — caught |
| add `WHERE return_1d IS NOT NULL` to fallback `with_momentum` | 2 failed — caught |
| add `WHERE return_1d IS NOT NULL` to adjusted `with_momentum` | 1 failed — caught |
| remove `WHERE rn = 1` from `with_splits` | 3 failed — caught |
| momentum window frame 20 → 21 | 2 failed — caught |
| remove benchmark from final GREATEST | 2 failed — caught |
| remove `AND ingest_ts <= :as_of` (bronze fallback) | 1 failed — caught |

## Checks run

- `python3 -m pytest tests/analytics_nl -q` (repo @HEAD) → **386 passed** (13.6s).
- `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest tests/analytics_nl -q` → **386 passed** (pyspark hidden).
- `python3 -m analytics_nl.export_schemas --check` → "All schemas match."
- Mutation dirs `/tmp/r18m{1,2,3,4,5,6,7,8,9,10,13,14}`: each a `git archive HEAD | tar -x` copy with a single DOC mutation → results above.
===VERDICT END===
