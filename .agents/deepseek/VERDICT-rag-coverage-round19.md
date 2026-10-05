===VERDICT START===
# VERDICT: rag-coverage rounds 19 + 19b — DeepSeek (checker)
**Status:** CHANGES_REQUESTED
**Round:** 19

## Summary

Full suite green (1172 passed, 36 skipped, 35.2 s), and every *named* mutation proof is
load-bearing — I applied each mutation to an independent `git archive HEAD` copy under
`/tmp/mut19` and the targeted test fails (details below). CIK overrides (r19 item 1),
foreign-filer forms (r19 item 2), the ownership-group no-abort change (r19b item 1), and the
two round-18 blockers (runbook `--catalog`/`--schema`; xbrl_client resolver) are all correctly
implemented and guarded. Two problems remain, one data-correctness and one SQL parameterization:

- **r19b item 2 is only half implemented.** The `--repair-cik-ownership` fix-up command exists,
  but the *ingest path itself* does **not** store the filer CIK from the accession prefix for new
  override-group filings. `_accession_filer_cik` is computed at
  `pipelines/sec_rag_ingest.py:1552` and thrown away (dead assignment). New filings are planned
  with the *iteration* CIK (first override CIK), so a legacy XOM filing is fetched from
  `data/2115436/…` and stored with `cik=0002115436` instead of `0000034088`.
- **`repair_cik_ownership` interpolates user-controlled `--tickers` values into SQL** via
  f-strings (`WHERE ticker = '{ticker}'`, `SET cik = '{correct_cik}'`), violating the
  parameterized-queries mandate.

## Blocking findings

- [pipelines/sec_rag_ingest.py:1585, 1718, 1729, 1173] Canonical stored CIK is not implemented for
  new override-group filings. `all_filings` is deduped per *ticker* (r19 discovery loop), but the
  anti-join iterates `for ticker, cik in mapped_tickers` (one entry per CIK) and does
  `planned.append((canonical, cik, canonical, filing))` using the iteration `cik`. Because
  `FilingMeta` carries no source CIK, the first CIK in the override group (e.g. `0002115436`)
  claims *all* of that ticker's deduped filings, including legacy filings whose accession prefix is
  `0000034088`. Consequences: `fetch_filing_text` builds `data/{int(cik)}/{acc}/{doc}` →
  `data/2115436/…` for a `0000034088-…` accession → 404 → `fetch_failed`; and `process_filing`
  stores `"cik": cik` + `filing_url` under the wrong CIK. The `filer_cik = _accession_filer_cik(dashed)`
  value at line 1552 is discarded, so r19b item 2 ("store the filer CIK actually present in the
  accession") is not satisfied — only the repair command half is. No test asserts this path
  (`test_canonical_stored_cik_from_accession_prefix` only exercises the two helper functions).
  → Concrete failure: an operator runs `--tickers XOM` against a clean target; the 7 legacy
  `0000034088-…` filings either fail to fetch (404) or are written with `cik=0002115436` and a
  `filing_url` pointing at `data/2115436/…`, which downstream silver/gold and retrieval would use.

- [pipelines/sec_rag_ingest.py:1868, 1890] `repair_cik_ownership` builds SQL by f-string
  interpolation of `ticker` (straight from `--tickers`, `ticker.strip().upper()` with no escaping),
  `cik_list`, `acc`, `current_cik`, and `correct_cik`. `--tickers "XOM'; DROP TABLE
  bronze_sec_filings_v2; --"` (or a ticker containing a single quote) breaks/injects the query.
  → Concrete failure: any ticker with a quote yields a syntax error or unintended statement; the
  existing Spark adapters (lines 1913, 2029–2062) only interpolate catalog/schema/view-name
  identifiers, never user input, so this is the first filter that puts user CLI input into SQL.

## Non-blocking notes

- **Dry-run counters are inconsistent — XOM 9/7/9 explained.** The anti-join (lines 1535–1586)
  iterates `mapped_tickers` (two entries for XOM) but reads the same deduped `all_filings["XOM"]`
  list each time, so the `planned_accessions` branch (1581–1583) inflates `skipped_existing_count`.
  With the live data (1 holdings filing + 8 legacy filings, one accession shared): discovered=9
  (raw `len(filings)` summed per CIK at 1486, **pre-dedup**), planned=7, skipped=9 (1 same-CIK +
  1 same-group + 7 re-iterated `planned_accessions`), failed=0 → `7+9 ≠ 9`. The correct figures are
  discovered=8 (deduped), planned=7, skipped=2. This is a reporting defect, not data corruption
  (the `planned` list itself is correctly deduped), but it shares a root cause with blocking #1 and
  makes the dry-run output misleading. `discovered_count` also over-counts any cross-CIK duplicate.
- [pipelines/sec_rag_ingest.py:1850] `group_map = _build_cik_group_map(cik_overrides)` in
  `repair_cik_ownership` is computed but never used (dead variable).
- `repair_cik_ownership` has no unit test — `test_repair_dry_run_does_not_write` only exercises the
  helpers and defers to Claude's integration run. Idempotency (skip when `current_cik == correct_cik`)
  and group-scoping (SELECT restricted to `ticker = '{ticker}' AND cik IN (group)`) hold by inspection,
  but the UPDATE at 1888–1893 does not itself constrain `ticker` (safe only because accession is
  unique), and it would rewrite a group row to a non-group CIK if an accession's prefix fell outside
  the override group.
- Round-19b "mutation" tests `test_mutation_drop_group_check_fails` / `test_mutation_re_raise_…`
  are not true mutations (they re-run the same happy path / test helpers); the real guard is
  `test_same_group_no_conflict` and `test_genuine_conflict_recorded_not_raised`, which I confirmed
  fail under actual source mutation (below).

## Verification of requested mutations (independent archive copies)

All mutations applied to `git archive HEAD` copies under `/tmp/mut19`, not the worktree.

- **r19 #1 (ignore overrides)** — `if sym_upper in overrides:` → `if False …` in `build_cik_map`:
  ```
  FAILED tests/rag/test_sec_rag_ingest.py::TestCikOverrides::test_build_cik_map_with_overrides
  FAILED tests/rag/test_sec_rag_ingest.py::TestCikOverrides::test_build_cik_map_override_takes_precedence
  FAILED tests/rag/test_sec_rag_ingest.py::TestCikOverrides::test_mutation_ignore_overrides_fails
  > assert ['0002115436'] == ['0002115436', '0000034088']
  ```
- **r19b #1a (drop group check)** — `if same_group:` → `if False:` (both sites):
  ```
  FAILED tests/rag/test_sec_rag_ingest.py::TestOwnershipGroup::test_same_group_no_conflict
  > assert 1 == 0   (same-group CIK recorded as a genuine conflict)
  ```
- **r19b #1b (re-raise instead of record)** — `result.failed_count += 1; continue` → `raise`:
  ```
  FAILED tests/rag/test_sec_rag_ingest.py::TestOwnershipGroup::test_genuine_conflict_recorded_not_raised
  FAILED tests/rag/test_sec_rag_ingest.py::TestOwnershipGroup::test_mutation_re_raise_instead_of_record_fails
  > pipelines.sec_rag_ingest.AccessionOwnershipConflict: MUT re-raise
  ```
- **r18 #4 (runbook `--catalog`/`--schema`)** — removed them from the first `sec_embeddings` line:
  ```
  FAILED tests/rag/test_sec_rag_ingest.py::TestRunbookBundleCommands::test_sec_embeddings_commands_have_catalog_schema
  > assert '--catalog' in '--ticker … --batch-size 256 --partitions 4'
  ```
- **r18 #5 (xbrl resolver)** — reverted `_get_user_agent` to `os.getenv("EDGAR_USER_AGENT", "")`:
  ```
  FAILED tests/rag/test_sec_rag_ingest.py::TestXbrlClientUserAgent::test_delegates_to_resolve_user_agent
  FAILED tests/rag/test_sec_rag_ingest.py::TestXbrlClientUserAgent::test_mutation_old_env_get_fails
  ```

## Other checks

- Foreign-filer chunking does not break 10-K/10-Q: `get_section_patterns` returns `SECTION_PATTERNS`
  for `10-K`/`10-Q`/`6-K` and `SECTION_PATTERNS_20F` only for `20-F`/`40-F`;
  `test_extract_sections_10k_still_works` passes and asserts no 20-F section names leak into 10-K.
- Default forms unchanged: `DEFAULT_FORMS = "10-K,10-Q"` (`pipelines/sec_rag_ingest.py:51`) and
  `--forms` default (`:2335`) untouched; the validation set was only widened to allow 20-F/40-F/6-K.

## Checks run

- `python3 -m pytest tests/rag tests/bronze -q --timeout 30` → **1172 passed, 36 skipped, 10 warnings** (35.16 s)
- Mutation r19#1 (ignore overrides) → **3 failed**
- Mutation r19b#1a (drop group check) → **1 failed**
- Mutation r19b#1b (re-raise) → **2 failed**
- Mutation r18#4 (runbook) → **1 failed**
- Mutation r18#5 (xbrl resolver) → **2 failed**
===VERDICT END===
