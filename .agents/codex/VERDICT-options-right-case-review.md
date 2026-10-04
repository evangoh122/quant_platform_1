===VERDICT START===
Status: CHANGES_REQUESTED

Branch: `fix/options-right-case` vs `origin/main`  
Findings: 2 blocking, 1 minor. Repository files were not modified.

1. BLOCKING — The production day writer is not tested (`notebooks/refresh_bronze_options.py:464,481-482`; `tests/gold/test_options_right_case.py:206-274`). Tests exercise `parse_opra_symbol()`, but production `_shape_day()` constructs `right` independently; `parse_opra_symbol()` has no production caller. Mutation changing `_shape_day()` back to lowercase survived: **41 passed**. Add a test against `_shape_day()` or refactor it to use directly tested canonicalization logic.

2. BLOCKING — The canonical-value contract remains inconsistent and undocumented (`docs/DATA_SCHEMAS.md:40,88`; `notebooks/01_ingest_market_data.py:243,264,286`; `gold/02_gold_options_features.sql:115,123`). `DATA_SCHEMAS.md` says only `string`; the refresh writes quotes as `call`/`put`, while the Quick Start ingestion notebook writes `C`/`P`. Gold’s `UPPER(right) = 'PUT'/'CALL'` handles case variants but not `P`/`C`, so p25/c25 can silently omit rows from that writer. Document each table’s allowed encoding and either retire/fix the `C`/`P` writer or accept both aliases in gold. Prefer one canonical Bronze encoding long-term. Silver 03/04 already normalize safely; no case-sensitive option-side consumers were found in `ml/`, `strategies/`, or `api/`.

3. MINOR — `sql/maintenance/2026-10-04_normalize_options_right_case.sql:37` ends with CRLF while the rest uses LF, contrary to the build’s LF requirement.

Correctness and maintenance assessment:

- All four changed gold comparisons correctly handle `PUT`/`put` and `CALL`/`call`.
- `put_volume`, `call_volume`, and `put_call_ratio` are recomputed from those corrected aggregates.
- The maintenance `UPDATE` is Delta-safe, backtick-quotes `right`, changes only exact lowercase `put`/`call`, and is idempotent.
- Gold 02 is a full-source `MERGE`, not date-incremental: it has no date predicate or range parameter. A rerun inserts the missing dates and updates existing rows.

Exact live rerun:

1. Execute `sql/maintenance/2026-10-04_normalize_options_right_case.sql` on the SQL warehouse and confirm the post-check has no lowercase `put`/`call`.
2. Run `python3 pipelines/run_silver_gold.py --only gold`. Do not use `--truncate`; no date parameter is needed.
3. Run `python3 pipelines/run_silver_gold.py --check`.
4. Verify `MAX(DATE(feature_ts))` reaches `2026-10-01` and inspect put/call totals from `2026-09-08` onward.

Tests:

- Targeted current branch: **41 passed**.
- Full suite with PySpark hidden: **202 passed, 22 skipped**.
- The requested normal full command was attempted, but the sandbox stalled at `test_refresh_bronze_cot.py::TestNaturalKey::test_anti_join_filters_existing_keys` while attempting Databricks Connect; it was interrupted after several minutes.
- Current tests over `origin/main` production: **6 failed, 2 passed**, confirming the principal gold/day regressions are detected.

Independent mutations:

1. Reverted one day-CTE `UPPER(right)` comparison: **3 failed, 5 passed** — mutation killed by the regex, DuckDB semantic, and repository scan tests.
2. Reverted production `_shape_day()` output to lowercase: **41 passed** — mutation survived, establishing finding 1.
===VERDICT END===
