===VERDICT START===
# VERDICT: rag-coverage round 19c — MiMo (builder)
**Status:** APPROVED
**Round:** 19c

## Summary

Both blocking findings from DeepSeek's round-19 verdict are resolved:

1. **Override-group filings now use filer CIK from accession prefix.** The anti-join
   loop (`sec_rag_ingest.py:1532–1594`) now iterates per unique ticker (not per
   ticker-CIK pair). For each filing, `_accession_filer_cik(dashed)` extracts the
   filer CIK from the accession prefix. If the filer CIK is in the ticker's override
   group, it is used as `plan_cik` for the planned tuple — so `fetch_filing_text`,
   `process_filing`, and the stored `cik`/`filing_url` all use the correct filer CIK.
   `discovered_count` now counts only deduped filings per ticker (pre/post length
   delta), so `planned + skipped_existing + failed == discovered` holds.

2. **`repair_cik_ownership` SQL fully parameterized.** All user-controlled values
   (tickers, CIKs, accessions) are passed via `?` positional parameters to
   `spark.sql(query, args=[...])`. Ticker validated against `^[A-Z][A-Z0-9.\-]{0,9}$`.
   UPDATE now constrains on `ticker` in addition to `accession_number` and `cik`.
   Group check uses `group_map` to refuse setting a CIK outside the override group.

3. **Fake mutation tests replaced.** `test_mutation_drop_group_check_fails` (was
   just helper assertions) replaced with `test_override_filings_use_filer_cik` and
   `test_counter_invariant_planned_plus_skipped_equals_discovered` — both exercise
   the full `run_ingest` path. `test_mutation_re_raise_instead_of_record_fails`
   retained (it does exercise `run_ingest` with a genuine conflict). Five new
   repair tests added with a fake `spark.sql` that captures SQL text and args.

## Blocking findings

None.

## Non-blocking notes

- The `planned_accessions` dedup in the anti-join uses `plan_cik` (the filer CIK)
  for the planned tuple, but the dedup key is the accession number — so two filings
  with the same accession but different filer CIKs (shouldn't happen in practice)
  would still be deduped. This is correct behavior since an accession uniquely
  identifies a filing.
- `repair_cik_ownership` still uses `DatabricksSession` at runtime — the fake
  spark tests cover the SQL generation and logic, but the actual `.collect()` call
  is integration-tested by the operator dry-run.

## Tests run

```
python -m pytest tests/rag/test_sec_rag_ingest.py tests/bronze -q --timeout 30
→ 463 passed, 17 skipped, 30.46s
```

## New test names and mutation proofs

| Test | Mutation that makes it fail |
|------|-----------------------------|
| `TestOwnershipGroup::test_override_filings_use_filer_cik` | Remove filer CIK logic in anti-join → legacy filing stored with holdings CIK → `assert legacy_rows[0]["cik"] == "0000034088"` fails |
| `TestOwnershipGroup::test_counter_invariant_planned_plus_skipped_equals_discovered` | Revert `discovered_count` to `+= len(filings)` → `discovered=3` but `planned+skipped+failed=2` → invariant breaks |
| `TestRepairCikOwnership::test_repair_dry_run_does_not_write` | Remove dry_run guard → UPDATE calls appear in `sql_calls` → `assert len(update_calls) == 0` fails |
| `TestRepairCikOwnership::test_repair_parameterized_sql` | Use f-string interpolation → `'XOM'` appears in SQL text → assertion fails |
| `TestRepairCikOwnership::test_repair_invalid_ticker_rejected` | Remove `_TICKER_RE.match` check → `XOM'; DROP TABLE t; --` accepted → no `ValueError` raised |
| `TestRepairCikOwnership::test_repair_idempotent_skip_when_correct` | Remove `current_cik == correct_cik` skip → UPDATE issued for already-correct row → `assert len(update_calls) == 0` fails |
| `TestRepairCikOwnership::test_repair_non_group_target_cik_refused` | Remove group check → UPDATE issued for out-of-group CIK → `assert len(update_calls) == 0` fails |
| `TestOwnershipGroup::test_mutation_re_raise_instead_of_record_fails` | (kept from r19b) Change `result.failed_count += 1; continue` to `raise` → `AccessionOwnershipConflict` raised |
===VERDICT END===