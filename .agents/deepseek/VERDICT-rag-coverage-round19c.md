===VERDICT START===
# VERDICT: rag-coverage round 19c — DeepSeek (checker)
**Status:** APPROVED
**Round:** 19c

## Summary

Both round-19 blocking findings are fixed and verified by independent mutation in
`git archive HEAD` copies under `/tmp/mut19c_*` (never the worktree). Full suite green.

1. **Filer CIK from accession prefix (blocking #1) — FIXED.** The anti-join
   (`pipelines/sec_rag_ingest.py:1537–1595`) now iterates `unique_tickers` once per
   ticker, not once per ticker-CIK pair. `discovered_count` is the deduped count
   (`:1482–1487`). For override tickers, `plan_cik` is set from
   `_accession_filer_cik(dashed)` when that prefix CIK is in the group
   (`:1583–1584`); when the prefix CIK is *not* in the group it logs a warning and
   keeps the iteration CIK (`:1585–1591`), per spec — no crash, not silent. Because
   `planned` now carries `plan_cik`, the fetch URL (`fetch_filing_text` `int(cik)`,
   `:1101`) and the stored `cik`/`filing_url` (`process_filing`, `:1160–1180`) all use
   the accession filer CIK.

2. **`repair_cik_ownership` parameterized (blocking #2) — FIXED.**
   (`pipelines/sec_rag_ingest.py:1840–1917`). Grep of the function body shows the only
   f-strings are the `{table}` identifier and the error message; ticker/CIK/accession
   values are bound via `?` positional markers with `spark.sql(query, args=[...])`
   (`:1878–1882`, `:1909–1913`). Ticker validated against `^[A-Z][A-Z0-9.\-]{0,9}$`
   (`:1854`, `:1868–1869`). UPDATE constrains `ticker` + `accession_number` + `cik`
   (`:1911`). `group_map` is now used to refuse a non-group target CIK
   (`:1894–1900`). Dry-run writes nothing (`:1902–1907`), idempotent
   (`current_cik == correct_cik` skip, `:1890–1892`).

## Blocking findings

None.

## Mutation verification (independent archive copies)

| Mutation (applied to `git archive HEAD` copy) | Test | Result |
|---|---|---|
| `plan_cik = filer_cik` → `plan_cik = next(iter(ticker_ciks))` (`:1584`) | `TestOwnershipGroup::test_override_filings_use_filer_cik` | **FAILED** (failed_count 1 — legacy filing 404) |
| `fetch_filing_text` URL `int(cik)` → hardcoded iteration CIK (`:1101`) | `TestOwnershipGroup::test_override_filings_use_filer_cik` | **FAILED** (failed_count 1) |
| Reintroduce f-string ticker `WHERE ticker = '{ticker}'` (`:1880`) | `TestRepairCikOwnership::test_repair_parameterized_sql` | **FAILED** (`'XOM'` literal in SQL) |
| Drop the group refusal (`correct_cik not in group_map...`, `:1894–1900`) | `TestRepairCikOwnership::test_repair_non_group_target_cik_refused` | **FAILED** (skipped 0 ≠ 1) |

## XOM counter scenario (ground truth)

Ran `run_ingest` (dry-run) with 1 holdings + 8 legacy, 1 shared accession, 1
already-present (temporary test in `/tmp/mut19c/tests/rag/test_tmp_counter19c.py`):

```
discovered 8   planned 7   skipped 1   failed 0
```

`planned + skipped + failed == discovered` (7+1+0 = 8) holds. Note: the round-19
verdict / BUILD figure "discovered=8, planned=7, **skipped=2**" is arithmetically
impossible under the invariant (7+2 ≠ 8); the correct value for *one* already-present
filing is `skipped=1`. No code defect — the counter logic is correct.

## API check (positional `?` markers)

- Installed `pyspark` 4.4.0.dev0: `SparkSession.sql(sqlQuery, args)` accepts a `list`
  and binds positional `?` markers (added in Spark 3.5.0). Verified via
  `inspect.signature`/`inspect.getsource`.
- `databricks-connect` 19.2.0 present; `DatabricksSession.builder.serverless(True)
  .getOrCreate()` returns the real `SparkSession`, whose `sql` is the Spark API above.
- `requirements.txt` does not pin `pyspark`/`databricks-connect` directly (they come
  transitively via `databricks-sdk`/Databricks runtime); the code pattern matches the
  existing Spark adapters in this file.

## Non-blocking notes

- [tests/rag/test_sec_rag_ingest.py:4058] `test_mutation_re_raise_instead_of_record_fails`
  was *not* removed despite the BUILD "Also" asking to replace *both* fake mutation
  tests. It is still a non-mutation (re-runs the same genuine-conflict happy path and
  asserts `failed_count >= 1`, duplicating `test_genuine_conflict_recorded_not_raised`).
  It does exercise shipped code (`run_ingest`), so it is not an inline re-implementation,
  but it is redundant and mislabeled. `test_mutation_drop_group_check_fails` *was* correctly
  removed and replaced with real tests.
- [pipelines/sec_rag_ingest.py:1585–1591] The "accession prefix CIK not in group" ingest
  fallback is correct by inspection (warns + keeps iteration CIK) but has **no dedicated
  test**. The `TestRepairCikOwnership` non-group test covers only the repair path, not the
  ingest planning path.
- [pipelines/sec_rag_ingest.py:1552] Dead comment `# Genuine conflict: record per filing,
  run continues` now sits after the `continue` inside the `existing_cik in ticker_ciks`
  branch and is unreachable.
- [pipelines/sec_rag_ingest.py:1542,1554,1585–1593] `next(iter(ticker_ciks))` iterates a
  `set`, so the "mapped CIK" used for the log message and the non-group fallback is
  non-deterministic across runs. Cosmetic/logging only — no correctness impact.

## Item 3 — are the retained/added tests real?

Yes. The five `TestRepairCikOwnership` tests call the shipped `repair_cik_ownership`
directly (with `databricks.connect` patched to a fake spark that captures `(query, args)`),
exercising the real control flow (dry-run/no-write, idempotency, ticker rejection, group
refusal, parameterization). `test_override_filings_use_filer_cik` and
`test_counter_invariant_planned_plus_skipped_equals_discovered` drive the full `run_ingest`
with fake HTTP/DB and assert the stored `cik`/`filing_url` and the counter invariant. None
re-implement the logic inline. The one exception is the retained
`test_mutation_re_raise_instead_of_record_fails` (see non-blocking note above).

## Checks run

- `python3 -m pytest tests/rag tests/bronze -q` → **1177 passed, 36 skipped** (37.6s)
- Mutation m1 (plan_cik → iteration CIK) → **1 failed**
- Mutation m2 (fetch URL → iteration CIK) → **1 failed**
- Mutation m3 (reintroduce f-string ticker) → **1 failed**
- Mutation m4 (drop group refusal) → **1 failed**
- XOM counter ground-truth → discovered=8, planned=7, skipped=1, failed=0
===VERDICT END===
