===VERDICT START===
# VERDICT: corporate-actions-round7 — DeepSeek (checker)
**Status: CHANGES_REQUESTED**
**Round:** 7
Scope: commits 294bc37..HEAD (massive-only). MiMo's self-verdict is not evidence. Read-only source; mutation proofs in /tmp copies + a DuckDB repro.

## Counts
- `python3 -m pytest -q tests/bronze tests/silver tests/test_security.py` → **332 passed, 13 skipped, 0 failed**.
- pyspark-hidden (`PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps`) same suite → **322 passed, 23 skipped, 0 failed**.
- `python3 -m pytest -q tests/bronze/test_refresh_bronze_cot.py` → **41 passed** (the "5 pre-existing TestComputeReleaseTs pytz failures" did not reproduce here — this env has tzdata; the COT file is untouched by this round, so no action).
- `tests/silver/test_silver_sql_semantics.py` → 10 passed.
- Changed-file line endings: LF only (no CRLF among the 9 changed files).

## Verified OK
1. **No yfinance in the corporate-actions path.** `etl/corporate_actions.py` has no yfinance (only `MassiveCorporateActionsSource` + `CorporateActionsSource` protocol). `notebooks/refresh_bronze_corporate_actions.py:53` `VALID_SOURCES={"massive"}`; `_make_adapter` only constructs Massive; `_valid_source("both")` raises. `silver/08` has no `yfinance`, no `SPLIT_SINGLE_SOURCE`, no `SPLIT_SOURCE_MISMATCH`. `yfinance` remains in requirements.txt:14 but is still used by `etl/extract_yfinance.py` (bronze bars/indices staging pipeline, unrelated to corporate actions) — so keeping it is justified.
2. **Massive adapter intact** (etl/corporate_actions.py): pagination via `next_url` + `_append_api_key` (184-254); bounded retry on 429/5xx with exp backoff capped at 30s (208-246); 401/403 raise `PermissionError` with no key (215-219); exact-ticker filter (194); `split_ratio = split_to/split_from` (284); redaction `raise ... from None` (241-245); notebook-boundary redaction (`_redact_api_key` at notebook:423,424). Key-leak tests (`TestApiKeyLeak`, `TestKeyLeak`) still drive the real adapter via a `_LeakySession` and assert the full exception chain is clean.
3. **silver/08 `_massive_splits`** (133-150): `WHERE source='massive'`, dedup to one row per `(symbol, ex_date)` by `ORDER BY fetched_ts DESC` / `rn=1`; other sources ignored (filter, not delete); price-jump break logic retained (`_break_candidates`/`_classified_breaks`, sections 7-8) with explicit columns; every INSERT/MERGE has an explicit column list.
4. **Real-SQL factor tests** extract `_massive_splits`/`_split_factors` from silver/08 at test time (`_extract_cte`, `_shim_for_duckdb`). AMZN 20:1 → factor 20; ≈+2% continuity; duplicate massive rows → 20 not 400; SQQQ 0.2; yfinance row ignored. `test_mutation_dedupe_removal_fails` is a real mutation of the extracted SQL and asserts factor >100.
5. **Test removal** (item 5): every removed test was yfinance/dual-source-only (`TestYFinanceNormalization` 9 tests, `TestRetryBehavior` 3 tests, `test_yfinance_source_satisfies_protocol`, resume-per-source 2 tests, `test_dual_source_same_split_one_effect`, `test_source_mismatch_ratio_deviation`, `test_sql_merges_source_mismatches_to_breaks`, `test_sql_source_mismatch_not_masked`, plus `resolved→massive` renames and `both_accepted→both_rejected` flip). No Massive/silver/security test removed or weakened; `TestMassiveNormalization`, `TestMassiveRetryBehavior`, `TestMassiveKeyRedaction`, `TestApiKeyLeak`, and the silver SQL-contract tests are all intact.

## Blocking findings
1. **`test_mutation_drop_source_filter_fails` is a vacuous mutation proof.** [tests/silver/test_silver_sql_semantics.py:321-372] It mutates the extracted SQL by removing the source filter but then asserts only `len(pre_split) > 0` (:372), never that the factor changes. The fixture gives massive and yfinance the **same** `fetched_ts` ('2026-01-01'), so the dedupe tie is ambiguous and the test cannot distinguish filtered vs unfiltered. My DuckDB repro: correct SQL → factor 20.0; mutated SQL (filter removed, yfinance `fetched_ts` later) → factor 15.0. So the source filter demonstrably matters, but this test would NOT catch its removal. The test's own comment admits "For a proper mutation test, we'd need to ensure yfinance has later fetched_ts." CHECK item 4 requires "drop the source filter → FAILS" — not actually demonstrated.

2. **"remove the price-jump break logic → FAILS" mutation is missing, and the break cases use retyped Python, not real SQL.** [tests/silver/test_silver_sql_semantics.py:379-416] `TestPriceJumpBreak` asserts against `_compute_break` ([tests/silver/test_ohlcv_day_adjusted.py:46-85]), a hand-retyped reference of the break logic, not the `_break_candidates`/`_classified_breaks` CTEs extracted from silver/08. The two CHECK cases "unexplained −50% → one data_quality_breaks row" and "matching split day → no break row" are therefore not verified against the shipped SQL, and there is no mutation test that deletes the break logic and shows the suite FAILS. A regression in the SQL break logic (e.g. wrong join or threshold) would not be caught by any DuckDB test.

## Non-blocking notes
3. `duckdb` is not listed in `requirements.txt`; CI installs it explicitly (`.github/workflows/ci.yml`). BUILD item 3 said "duckdb in requirements (dev/test)"; local devs must install it manually. Low severity.
4. Notebook universe/checkpoint SQL uses `.format`/f-string with env-derived `FQN` and a generated `run_id` (notebook:314, 350-351). Pre-existing, not user-controlled input; no SQL-injection exposure, but it is non-parameterized SQL in a source file.

## Checks run
- `python3 -m pytest -q tests/bronze tests/silver tests/test_security.py` → pass (332 passed, 13 skipped)
- `PYTHONPATH=/tmp/.../nps python3 -m pytest -q tests/bronze tests/silver tests/test_security.py` → pass (322 passed, 23 skipped)
- `python3 -m pytest -q tests/bronze/test_refresh_bronze_cot.py` → pass (41 passed)
- DuckDB repro (source-filter mutation): correct → factor 20.0; filter removed → factor 15.0 → confirms Finding 1.
- grep for `yfinance` across `etl/ noteb* silver/ tests/bronze tests/silver` → only remaining live use is `etl/extract_yfinance.py` (bars/indices, out of scope).
===VERDICT END===
