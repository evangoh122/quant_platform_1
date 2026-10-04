===VERDICT START===
# VERDICT: corporate-actions-round8 — DeepSeek (checker)
**Status: APPROVED**
**Round:** 8
Scope: commits 53aab88..HEAD (MiMo's test-gap fixes only). Read-only source; mutation proofs in /tmp/ca8-mut-* copies. MiMo's self-verdict is not evidence.

## Counts
- `python3 -m pytest -q tests/bronze tests/silver tests/test_security.py` → **336 passed, 13 skipped, 0 failed**.
- pyspark-hidden (`PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps`) same suite → **326 passed, 23 skipped, 0 failed**.
- `python3 -m pytest -q tests/silver/test_silver_sql_semantics.py` → **14 passed** (10 original + 4 new `TestPriceJumpBreakSQL`).
- `python3 -m pytest -q tests/silver/test_silver_sql_semantics.py -k mutation -v` → **3 passed** (dedupe-removal, source-filter-drop, break-predicate-required).
- Changed files (requirements.txt, tests/silver/test_silver_sql_semantics.py): LF endings, no CRLF. No secrets.

## Verified OK (round-7 repros, exactly)

### 1. Source filter — now a real mutation proof
[tests/silver/test_silver_sql_semantics.py:329-383] `test_mutation_drop_source_filter_fails` rewritten:
fixture massive AMZN 20.0 `fetched_ts` 2026-01-01 + yfinance AMZN 15.0 `fetched_ts` 2026-02-01 (LATER). Positive: real SQL → factor **exactly 20.0** (line 370 asserts 20.0). Mutation in /tmp/ca8-mut-srcfilter (removed `WHERE source = 'massive'` from silver/08 `_massive_splits`) → test **FAILS**: `AssertionError: Positive: factor for 2022-06-01 should be 20, got 15.0`. Filter is load-bearing. **Round-7 Finding 1 resolved.**

### 2. Break logic tested against the REAL SQL
New `TestPriceJumpBreakSQL` extracts `_adjusted`, `_break_candidates`, `_classified_breaks` from silver/08 at test time (`_extract_cte` + `_shim_for_duckdb`) and runs them in DuckDB (`_run_break_ctes`).
- (a) unexplained −50%, no split → exactly one row `UNEXPLAINED_PENDING`, `is_masked=True`, `split_error≈0.5` [test:551-564] → passed.
- (b) AMZN 20:1 matching ~+2% adjusted move → one row `SPLIT_EXPLAINED`, `is_masked=False`, `split_error≤0.03` [test:566-578] → passed (see non-blocking note 1).
- (c) mismatched split day (`SPLITBAD` 20:1, raw move ≠ ratio) → exactly one row `UNEXPLAINED_PENDING`, `is_masked=True` [test:580-592] → passed; the "mismatched split day" case (BUILD item 2c) exists.
- Mutation in /tmp/ca8-mut-break (`AND ABS(a.raw_gross_return - 1.0) >= 0.40` → `AND 1 = 0`) → **all 4 break tests FAIL** (a, b, c, and the in-memory mutation test).
- Python reference tests (`TestPriceJumpBreak` → `_compute_break`) kept unchanged [test:390-427]. **Round-7 Finding 2 resolved.**

### 3. duckdb in requirements.txt
`requirements.txt:17` adds `duckdb>=0.10.0`. **Resolved.**

### 4. Bronze timeout / Databricks connectivity
`python3 -m pytest -q tests/bronze` → **244 passed, 10 skipped, 0 failed in ~30s**. No timeout reproduced. The only Databricks-Connect references are pre-existing fixtures: `tests/bronze/test_refresh_bronze_cot.py:47` (`DatabricksSession.builder.serverless(True)` fallback to local) and `tests/bronze/test_refresh_bronze_options.py:512` (`_FakeSparkSession`). `git diff --name-only 53aab88..HEAD -- tests/bronze` → **empty**; `git log 53aab88..HEAD -- tests/bronze` → **empty**. This branch introduced nothing in bronze.

### 5. No tests deleted/weakened
`git diff 53aab88..HEAD -- tests` touches only tests/silver/test_silver_sql_semantics.py (+214/−23). The sole removed test is the old vacuous `test_mutation_drop_source_filter_fails` (which asserted `len(pre_split) > 0`), replaced by the strict version above. `TestYfinanceRowIgnored`, `TestAMZNSplit`, `TestDuplicateMassiveRows`, `TestSQQQReverseSplit`, `TestKeyLeak`, `TestPriceJumpBreak` all intact.

## Blocking findings
(none)

## Non-blocking notes
1. Request item 2 wording "matching split day → none": the test asserts **one** `SPLIT_EXPLAINED` row with `is_masked=False`, not zero rows. This is the correct real-SQL behaviour — silver/08 `_classified_breaks` (line 268-277) emits a `SPLIT_EXPLAINED` row for every candidate whose same-date split explains it; the MERGE (line 330) inserts it with `is_masked=FALSE`, so it does not mask `return_1d`. Asserting `len==0` would be impossible against correct SQL. The semantic intent ("no masked/unexplained break") is verified via `classification=='SPLIT_EXPLAINED'` and `is_masked==False`. Test name `test_split_day_adjusted_move_matches_no_break` is slightly misleading only.
2. Bronze `spark()` fixture (test_refresh_bronze_cot.py:43-66) still attempts Databricks Connect serverless before local fallback; pre-existing and out of scope for this round.

## Checks run
- `python3 -m pytest -q tests/bronze tests/silver tests/test_security.py` → pass (336/13)
- `PYTHONPATH=/tmp/.../nps python3 -m pytest -q tests/bronze tests/silver tests/test_security.py` → pass (326/23)
- `python3 -m pytest -q tests/silver/test_silver_sql_semantics.py` → pass (14)
- `python3 -m pytest -q tests/bronze` → pass (244/10)
- Mutation srcfilter (/tmp/ca8-mut-srcfilter) → 1 failed (`...got 15.0`)
- Mutation breakfalse (/tmp/ca8-mut-break) → 4 failed
- `git diff 53aab88..HEAD -- tests/bronze` → empty (no bronze changes)
===VERDICT END===
