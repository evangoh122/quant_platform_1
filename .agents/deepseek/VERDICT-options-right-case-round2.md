===VERDICT START===
# VERDICT: options-right-case round 2 — DeepSeek (checker)

**Status:** APPROVED
**Round:** 2
**Commits checked:** c3a844a..HEAD (4670190, 2ec2a9b, d1a3f0c, 1dd833c, fec7241)
**Branch:** `fix/options-right-case`; `main` untouched. No Databricks access used.

## Blocking findings

None.

## Verification (all 5 items)

1. **QUOTES path lowercase / DAY path uppercase** — PASS.
   - `notebooks/refresh_bronze_options.py:247-259` `_right_from_contract_type` returns `'call'`/`'put'`
     (quotes path via `shape_quote_row`). Day path stays uppercase:
     `parse_opra_symbol` returns `"CALL"`/`"PUT"` (line 206); `_shape_day` emits
     `F.lit("CALL")`/`F.lit("PUT")` (lines 481-482).
   - Both paths asserted: `tests/gold/test_options_right_case.py:262`
     `test_quotes_path_lowercase_day_path_uppercase`, plus `:206` (day) and
     `:215`/`:226` (quotes). Bronze day-path tests still assert uppercase
     (`tests/bronze/test_refresh_bronze_options.py:28,38`), quotes-path assert lowercase
     (`:188,204,232-235`).
   - **Mutation (make quotes path uppercase, /tmp/optcase2-mut-a):** `6 failed, 35 passed` —
     `test_right_from_contract_type_emits_lowercase`,
     `test_shape_quote_row_right_lowercase`, `test_quotes_path_lowercase_day_path_uppercase`,
     `test_shape_quote_row_full`, `test_shape_quote_row_right_put`,
     `test_shape_quote_row_right_normalisation`.

2. **DuckDB test extracts `day` CTE from gold/02** — PASS.
   - `tests/gold/test_options_right_case.py:49-128` `_extract_day_cte` parses
     `WITH day AS (` to the matching close-paren from `gold/02_gold_options_features.sql`
     read at test time; `_DAY_QUERY` appends only the outer `SELECT ... FROM day`. No retyped copy.
   - Documented shims: (a) availability `convert_timezone(...)+make_interval(...)` → literal,
     (b) `universe` subquery removed, (c) fully-qualified table name → bare fixture name,
     (d) `right` backtick→`"right"` (DuckDB reserved function). All four documented in the
     docstring; (c)/(d) are additive to the two named in the BUILD request but do not mask the
     mutation (proven below).
   - DuckDB tests **RUN, not skipped**: `pytest.importorskip("duckdb")` and duckdb 1.5.6 is
     installed here. `python3 -m pytest -v tests/gold/test_options_right_case.py` → 8 passed,
     none skipped. The 12 skips in the full run are all `db.database (DuckDB) removed; Delta is
     the store` (the removed DuckDB *store*, unrelated to the `duckdb` package).
   - CI installs duckdb: `.github/workflows/ci.yml:44` (`pip install ... duckdb ...`). Confirmed.
   - **Mutation (revert one UPPER in gold/02, /tmp/optcase2-mut-b):** `3 failed` —
     `test_day_cte_counts_all_case_variants` (DuckDB semantic), `test_gold_sql_right_comparisons_are_case_insensitive`,
     `test_repo_wide_no_case_sensitive_right_comparisons`.

3. **Repo-wide scan covers .py + .sql** — PASS.
   - `tests/gold/test_options_right_case.py:288-289`: `.py` dirs
     `pipelines, ml, strategies, api, analytics_nl, notebooks`; `.sql` dirs
     `silver, gold, pipelines`; excludes `tests/` and `.agents/`.
   - **Mutation (plant `WHERE right = 'PUT'` in `pipelines/run_silver_gold.py`, /tmp/optcase2-mut-c):**
     `test_repo_wide_no_case_sensitive_right_comparisons` FAILED →
     `pipelines/run_silver_gold.py:14200: right = 'PUT'`.

4. **Maintenance SQL** — PASS.
   - `sql/maintenance/2026-10-04_normalize_options_right_case.sql`: `` `right` `` backtick-quoted
     in SELECT/WHERE/GROUP/SET/UPDATE (lines 21-37); trailing newline present (`od -c` ends
     `;\r\n`); idempotent (`SET \`right\` = UPPER(\`right\`) WHERE \`right\` IN ('put','call')`);
     pre-check SELECT (20-25) and post-check SELECT (32-37); header notes the deliberate one-off
     exception to `docs/BRONZE_REFRESH_PLAN.md:13` (lines 3-4), matching the "no Bronze UPDATE"
     rule there.

5. **Only the tautological test removed** — PASS.
   - `git diff c3a844a..HEAD -- tests` removes only `test_mutation_proof_revert_upper_fails`
     (allowed). `test_right_from_contract_type_emits_uppercase` → `_emits_lowercase` and
     `test_shape_quote_row_right_uppercase` → `_lowercase` are renames with expectations corrected
     to the new (lowercase) quotes contract — required by item 1, not weakenings. Added
     `test_extracted_day_cte_contains_upper` and `test_quotes_path_lowercase_day_path_uppercase`.
     Only 2 test files changed.

## Test runs

- `python3 -m pytest -q tests/gold tests/bronze tests/silver` → **212 passed, 12 skipped** (20.1s).
  No `pytz ModuleNotFoundError` failures: system python3 (3.12.3) has pytz 2024.1 installed, so the
  7 pre-existing pytz failures observed earlier under `/tmp/h8-venv` (which lacks pytz) do not occur.
- pyspark-hidden `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps`
  → **202 passed, 22 skipped** (10 extra skips are `PySpark not available`, expected).
- `python3 -m pytest -v tests/gold/test_options_right_case.py` → **8 passed** (DuckDB tests run).

## Non-blocking notes

- `_extract_day_cte` applies 4 documented shims; (c) table de-qualify and (d) `` `right` ``-quoting
  are beyond the two named in `BUILD-options-right-case-round2.md` item 2, but they are necessary
  for DuckDB execution, documented in the docstring, and do not mask a UPPER-revert mutation
  (mutation B still fails `test_day_cte_counts_all_case_variants`).
- MiMo's self-verdict ("12 skipped (DuckDB-removal skips)") is accurate: those 12 skips are the
  removed `db.database` store, not the `duckdb` package; the options-right-case DuckDB tests run
  in both the local env and CI.
===VERDICT END===
