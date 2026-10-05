# VERDICT: xbrl-B1b — MiMo
**Status:** APPROVED
**Round:** 5

## Blocking findings
- None.

## Non-blocking notes
- All nullable natural-key columns in the MERGE ON clause now use `<=>` (Spark null-safe equality). COALESCE sentinel patterns removed — `<=>` handles NULL correctly without them.
- New test helpers `_get_full_merge_sql()` and `_run_silver_merge()` execute the actual MERGE (translated to `IS NOT DISTINCT FROM` for DuckDB), not just the extracted INSERT source.
- Mutation proof: replacing `<=>` with `=` for `accession_number` causes duplicate inserts on rerun when `accession_number` is NULL (count 1→2).
- Existing 15 tests unaffected; 3 new idempotency tests added (18/18 pass).

## Checks run
- `python3 -m pytest tests/silver/test_sec_xbrl_facts.py -v` → 18 passed in 1.48s
- Mutation proof script (production `<=>` idempotent 1→1, mutated `=` duplicates 1→2) → pass
- `git diff --cached --stat` → 2 files changed, 239 insertions, 13 deletions
- Commit: `f4f7f0b` on `feat/xbrl-silver`