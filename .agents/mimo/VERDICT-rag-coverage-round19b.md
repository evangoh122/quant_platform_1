# VERDICT: rag-coverage-round19b — MiMo
**Status:** APPROVED
**Round:** 19b

## Summary
Fixed `AccessionOwnershipConflict` false positive for multi-CIK override tickers (XOM). CIKs in the same `sec_cik_overrides.yaml` group are now treated as ONE ownership group. Genuine conflicts (unrelated CIK/ticker) are recorded as failed audit rows and the run continues — never aborts.

## Changes made

### `pipelines/sec_rag_ingest.py`
- **`_accession_filer_cik()`** — extracts 10-digit CIK prefix from accession number (e.g. `0000034088-26-000093` → `0000034088`)
- **`_build_cik_group_map()`** — builds CIK → ownership-group frozenset from override config; CIKs listed together for the same ticker form one group
- **Anti-join (Site A, ~line 1541)** — group-aware check: same-group → skip (no conflict); genuine conflict → record failed audit row + `result.failed_count += 1` + continue (no raise)
- **Race-path (Site B, ~line 1676)** — same pattern: same-group → skip; genuine conflict → record + return (no raise)
- **`repair_cik_ownership()`** — idempotent fix-up: rewrites stored CIKs for override-group tickers to the filer CIK from accession prefix. Supports `--dry-run`
- **CLI** — `--repair-cik-ownership` argument wired into `main()`, requires `--tickers`

### `tests/rag/test_sec_rag_ingest.py`
- **Updated `test_different_cik_accession_raises_conflict`** — now expects `result.failed_count >= 1` (conflict recorded, not raised)
- **Updated `test_race_path_conflict_raises`** — same: conflict recorded, not raised
- **Updated `test_ownership_conflict_writes_failed_log_entry`** — checks audit row written AND `result.failed_count >= 1`
- **New `TestOwnershipGroup`** (6 tests):
  - `test_same_group_no_conflict` — XOM accession stored under 2115436, request from 34088 → skipped, no failure
  - `test_genuine_conflict_recorded_not_raised` — unrelated CIK → filing fails, run continues
  - `test_genuine_conflict_writes_audit_row` — checks audit row with `error_code=ownership_conflict`
  - `test_mutation_drop_group_check_fails` — verifies group map is the key enabler
  - `test_mutation_re_raise_instead_of_record_fails` — genuine conflict must not raise
  - `test_canonical_stored_cik_from_accession_prefix` — filer CIK extraction + group identity
- **New `TestRepairCikOwnership`** (4 tests):
  - `test_accession_filer_cik` — CIK extraction from accession numbers
  - `test_build_cik_group_map` — group frozenset construction + identity
  - `test_build_cik_group_map_empty` — empty/None → empty map
  - `test_repair_dry_run_does_not_write` — repair logic verification via helpers

## Mutation proofs
1. **Drop group check** → `test_same_group_no_conflict` FAILS (same-group CIKs falsely conflict)
2. **Re-raise instead of record** → `test_genuine_conflict_recorded_not_raised` FAILS (run aborts)
3. **Drop `_build_cik_group_map`** → `test_build_cik_group_map` FAILS (empty map returned)

## Checks run
- `python3 -m pytest tests/rag/test_sec_rag_ingest.py -q` → 187 passed, 6 skipped
- `python3 -m pytest tests/bronze -q` → 260 passed, 22 skipped

## Commit
`d1134e2` on `slice/rag-coverage` — 2 files changed, 464 insertions, 50 deletions

## Non-blocking notes
- `SparkDataWriter` batch/pre-MERGE conflict checks (Site C) are unchanged — they are data-integrity safety nets that still raise `AccessionOwnershipConflict`. The anti-join deduplicates same-group accessions before they reach the writer.
- The `--repair-cik-ownership` command uses `DatabricksSession` (production Spark); integration-tested by Claude's XOM dry-run re-run.