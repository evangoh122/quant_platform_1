===VERDICT START===
# VERDICT: options-right-case round 3 — DeepSeek (checker)

**Status:** APPROVED
**Round:** 3
**Commits checked:** 8af3d7f..HEAD (3a1902d, b01430e, 2c9dff3)
**Branch:** `fix/options-right-case`; `main` untouched. No Databricks access used. Read-only on the repo; all mutation proofs run in `/tmp/optcase3-mut-*` copies.

## Blocking findings

None.

## Verification (all 5 items)

1. **`_shape_day()` uses ONE directly tested canonicalisation function; a test runs `_shape_day()` itself** — PASS.
   - `notebooks/refresh_bronze_options.py:247-264` `canonical_day_right(raw)` maps `PUT/put/P → 'PUT'`, `CALL/call/C → 'CALL'`, else `None`. It is the single source of truth.
   - `_shape_day` (`:484-530`) wraps it exactly once as a UDF at `:495`
     `_day_right_udf = F.udf(canonical_day_right, StringType())` and emits it at
     `:508` `_day_right_udf(F.regexp_extract("ticker", pattern, 3)).alias("right")`.
   - Direct unit tests: `tests/bronze/test_refresh_bronze_options.py` `test_canonical_day_right_call_variants`,
     `test_canonical_day_right_put_variants`, `test_canonical_day_right_rejects_unknown`.
   - `_shape_day()` itself is exercised by `test_shape_day_emits_uppercase_right` (`:92-131`):
     it calls `m._shape_day(...)` against a mocked Spark chain and asserts
     `captured_udf_fn is m.canonical_day_right` plus uppercase outputs `C/P/c/p → CALL/PUT`.
   - **Codex's exact mutation** (make the canonicalisation emit lowercase 'put'/'call',
     `/tmp/optcase3-mut-1a`): **3 failed, 34 passed** —
     `test_canonical_day_right_call_variants`, `test_canonical_day_right_put_variants`,
     `test_shape_day_emits_uppercase_right` (assertion `'call' == 'CALL'`).

2. **gold/02 day CTE and p25/c25 quote CTEs map all encodings; DuckDB fixtures carry P/C and the extracted SQL counts them** — PASS.
   - Day CTE: `gold/02_gold_options_features.sql:73-74`
     `SUM(CASE WHEN UPPER(right) IN ('PUT','P') …)`, `… IN ('CALL','C') …`.
   - p25: `:115` `WHERE UPPER(right) IN ('PUT','P')`; c25: `:123` `WHERE UPPER(right) IN ('CALL','C')`.
   - Fixture rows added: `tests/gold/test_options_right_case.py:169-176`
     (`AAPL 2026-09-03 'P'/'C'`, `SPY 2026-09-02 'P'/'C'`); assertions `:194-199` expect
     put_volume=50/call_volume=75 (AAPL) and 120/180 (SPY).
   - **Mutation** (drop `'P'` from the day put alias AND the p25 alias, `/tmp/optcase3-mut-2`):
     `test_day_cte_counts_all_case_variants` **FAILED** (`assert 0 == 50`). **1 failed, 8 passed.**
   - Caveat (see non-blocking note): dropping `'P'`/`'C'` from p25/c25 *only* leaves all 9 gold tests passing.

3. **docs/DATA_SCHEMAS.md lists per-writer encodings + consumer normalisation rule** — PASS.
   - `docs/DATA_SCHEMAS.md:40` (quotes) and `:65` (trades): `'call'/'put'` (quotes path), `'C'/'P'` (Quick Start).
   - `:88` (day): `'PUT'/'CALL'` (day-agg path), `'put'/'call'` (leakage), `'P'/'C'` (Quick Start)
     plus the shared `CASE WHEN UPPER(right) IN ('PUT','P') THEN 'PUT' … 'CALL' END` rule.
   - Quick Start writer confirmed: `notebooks/01_ingest_market_data.py:243`
     `right = ctype.upper()[:1]` → `'C'`/`'P'`; left unchanged as required.

4. **Maintenance SQL is LF; CRLF reintroduction is caught** — PASS.
   - `sql/maintenance/2026-10-04_normalize_options_right_case.sql`: `file` → UTF-8 text; zero `\r` bytes
     (`grep -c $'\r'` → 0).
   - Guard: `tests/gold/test_options_right_case.py:353-366` `test_no_crlf_in_maintenance_sql`.
   - **Mutation** (convert file to CRLF, `/tmp/optcase3-mut-3`): **FAILED** —
     `Found CRLF line endings in: sql/maintenance/2026-10-04_normalize_options_right_case.sql`.

5. **No tests deleted/weakened** — PASS.
   - `git diff 8af3d7f..HEAD -- tests/` → 110 insertions, 2 deletions. The two `-` lines are:
     (a) a `day_fixture` row re-emitted with only a trailing comma added to append P/C rows, and
     (b) a docstring updated to include P/C. Both are additions/edits, not weakenings.
     Net new tests: `test_canonical_day_right_*` (3), `test_shape_day_emits_uppercase_right`,
     `test_no_crlf_in_maintenance_sql` = 5, matching the 212→217 pass-count increase.

## Test runs

- `python3 -m pytest -q tests/gold tests/bronze tests/silver` → **217 passed, 12 skipped** (19.5s).
- pyspark-hidden `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps`
  → **206 passed, 23 skipped** (2.7s).

## Non-blocking notes

- **p25/c25 have no dedicated semantic test.** The only DuckDB semantic test extracts the `day` CTE
  (`bronze_options_day`); the p25/c25 CTEs read `bronze_options_quotes` and are verified only by the
  UPPER-wrapping regex scan. Dropping the `'P'`/`'C'` alias from p25/c25 *alone* (day CTE intact,
  `/tmp/optcase3-mut-2b`) yields **9 passed** — no failure. The SQL is correct today, but a future
  regression confined to p25/c25 would be silent. Consider a quotes-table DuckDB fixture + p25/c25
  assertion in a later round if coverage parity with the day CTE is desired.
- `test_shape_day_emits_uppercase_right` proves `canonical_day_right` is wrapped as a UDF and that
  `canonical_day_right` returns uppercase, but it does not assert the UDF output is actually the
  emitted `right` column. A contrived mutation that keeps the `_day_right_udf = F.udf(...)` line but
  replaces its use in `.select()` with an inline lowercase `F.when` (`/tmp/optcase3-mut-1`) is **not**
  caught (`1 passed`). This is cosmetic; the realistic lowercase regression (Codex's mutation) is
  caught by item 1 above.
===VERDICT END===
