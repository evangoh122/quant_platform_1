# BUILD-REQUEST: bronze-cot — ROUND 2

**Branch:** `slice/bronze-cot` · **Builder:** MiMo · **Checkers:** Claude, then DeepSeek
Read `.agents/codex/VERDICT-bronze-cot.md`.

The **live data is correct** — coordinator verified +292 rows per table, 0 duplicate keys,
append-only history, current to CFTC's latest published report (2026-09-22). **Do not re-run
`--write` against the live tables unless a fix requires it, and never with overwrite.** Codex
confirmed the key and the release-time rule (`report_date + 6 days 15:30 NY`). Keep them.

## Fix
1. **Never overwrite.** `notebooks/refresh_bronze_cot.py:455,460` creates a missing table with
   `.mode("overwrite")`. Create it with `CREATE TABLE IF NOT EXISTS` / `.mode("append")` only.
2. **Verify before success.** After each append (`:455-470`), assert
   `post_count - pre_count == appended_count`, all expected keys present, and zero duplicate keys;
   only then set status OK. Otherwise FAILED, nonzero exit.
3. **Off-by-one.** `:407` sets `start_date = max(report_date) + 1 day` but `:531` filters
   `report_date > start_date`, so a report exactly one day later is skipped. Make it `>=`
   (or keep `start = max` with `>`); add a test with a report dated max+1.
4. **Tests must call production code.** Replace tautological tests (`tests/bronze/test_refresh_bronze_cot.py:153,182,256`)
   with tests that call `validate_contract_code_column`, `anti_join_new_rows`,
   `detect_revision_conflicts`, and the `to_bronze` parsing path. Each must fail if that function
   were broken.

Verify: `python3 -m pytest tests/bronze/test_refresh_bronze_cot.py -q` and a `--dry-run` showing
**0 new rows** against the live tables (they are current). Paste both.
Edit only `notebooks/refresh_bronze_cot.py` and `tests/bronze/test_refresh_bronze_cot.py`.
LF line endings. **Commit your work.** Write `.agents/mimo/VERDICT-bronze-cot-round2.md`.
