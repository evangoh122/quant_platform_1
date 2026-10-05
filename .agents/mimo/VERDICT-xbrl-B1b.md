# VERDICT: xbrl-B1b — MiMo
**Status:** APPROVED
**Round:** 1

## Blocking findings
- None

## Non-blocking notes
- DuckDB testing approach used instead of Spark for hermetic tests (no network dependency)
- The silver SQL uses MERGE which requires Databricks Spark; DuckDB tests simulate equivalent logic
- PIT view SQL provided as template; Python helper `asof_facts()` in `db/xbrl_queries.py` for API use

## Checks run
- `pytest -q tests/silver/test_sec_xbrl_facts.py` → 15 passed (1.20s)

## Files created/modified

### New files
1. **`silver/09_silver_sec_xbrl_facts.sql`** — Silver transform: normalizes CIK/ticker/concept/unit/dates/numerics, resolves `information_available_ts` via join to `bronze_sec_filings_v2.accepted_ts`, deduplicates repeated ingestions on natural key, keeps restatements as separate rows, flags unresolved accessions with `quality_status = 'unresolved_accession'`

2. **`silver/09_silver_sec_xbrl_facts_asof.sql`** — PIT query template: filters `information_available_ts <= :as_of`, picks latest per (cik, taxonomy, concept, unit, period) ordered by `information_available_ts DESC, filed_date DESC, accession_number DESC`

3. **`db/xbrl_queries.py`** — Python helper `asof_facts(spark, as_of, ...)` with parameterized query, optional filters (cik, ticker, concept, taxonomy), and row cap

4. **`tests/silver/test_sec_xbrl_facts.py`** — 15 tests covering:
   - Reingest dedup (no duplicates)
   - First/last observed timestamps preserved
   - Two accessions same period both survive (restatements)
   - `information_available_ts` equals `accepted_ts`
   - Unresolved accession excluded from PIT/gold
   - As-of before amendment returns original value
   - As-of after amendment returns amended value
   - Named mutations: acceptance_time→filed_date, drop accession from key, sort oldest-first, publish unresolved

5. **`tests/silver/conftest.py`** — Network socket guard (autouse) matching `tests/bronze/conftest.py`

### Modified files
1. **`pipelines/run_silver_gold.py`** — Added `silver_sec_xbrl_facts` step after `data_quality_breaks` in STEPS and TARGET_TABLES

## Requirements coverage (§2.3, §2.5 items 3-5)

| Requirement | Status | Evidence |
|-------------|--------|----------|
| §2.3: Normalize CIK/ticker/concept/unit/dates | ✅ | SQL normalization + `TestNormalization` (4 tests) |
| §2.3: information_available_ts = accepted_ts | ✅ | `TestInformationAvailableTs::test_information_available_ts_equals_accepted_ts` |
| §2.3: Unresolved accession flagged, excluded from PIT | ✅ | `TestInformationAvailableTs::test_unresolved_accession_not_published` |
| §2.3: Dedupe repeated ingestions, keep latest | ✅ | `TestIdenticalReingest::test_no_duplicate_on_identical_reingest` |
| §2.3: First/last observed timestamps | ✅ | `TestIdenticalReingest::test_first_last_observed_preserved` |
| §2.3: Different accessions = different facts | ✅ | `TestRestatementsKept::test_two_accessions_same_period_both_survive` |
| §2.5 item 3: Reingest no duplicate | ✅ | `TestIdenticalReingest::test_no_duplicate_on_identical_reingest` |
| §2.5 item 3: Two accessions survive | ✅ | `TestRestatementsKept::test_two_accessions_same_period_both_survive` |
| §2.5 item 4: info_ts = accepted_ts | ✅ | `TestInformationAvailableTs::test_information_available_ts_equals_accepted_ts` |
| §2.5 item 4: Unresolved not published | ✅ | `TestInformationAvailableTs::test_unresolved_accession_not_published` |
| §2.5 item 5: As-of before amendment | ✅ | `TestAsOfAmendment::test_asof_before_amendment_returns_original` |
| §2.5 item 5: As-of after amendment | ✅ | `TestAsOfAmendment::test_asof_after_amendment_returns_amended` |

## Named mutation evidence

| Mutation | Test | How it fails |
|----------|------|--------------|
| acceptance time → filed_date | `test_mutation_acceptance_time_replaced_with_filed_date` | filed_date (Mar 10) ≠ accepted_ts (Mar 15) |
| drop accession from key | `test_mutation_drop_accession_from_key` | Without accession, dedup collapses 2 rows → 1 |
| sort restatements oldest-first | `test_mutation_sort_restatements_oldest_first` | Oldest-first returns original (394B) not amended (395B) |
| publish unresolved | `test_mutation_publish_unresolved_accessions` | Unresolved with fabricated ts leaks into PIT results |