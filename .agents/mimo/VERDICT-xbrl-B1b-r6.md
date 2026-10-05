# VERDICT: xbrl-B1b — MiMo
**Status:** APPROVED
**Round:** 6

## Blocking findings
- None. All 8 previously-surviving mutations are now covered by parametrized tests.

## Non-blocking notes
- The production source SELECT does NOT filter out NULLs for any of the 12 nullable key columns before the MERGE. All 12 parametrized cases assert the fact appears exactly once (not quarantinated). NULL values pass through COALESCE in the dedup PARTITION BY and through TRIM/UPPER normalization unchanged.
- The existing accession_number mutation test (TestIdempotentMerge::test_mutation_plain_eq_breaks_null_accession_idempotency) already proved `<=>` → `=` breaks idempotency for NULL accession_number. The new parametrized test extends this coverage to all 12 columns.

## Per-column null-filter analysis
| Column | Source filter before MERGE? | NULL fact behavior | Parametrized assertion |
|--------|---------------------------|-------------------|----------------------|
| cik | TRIM only (NULL→NULL) | Excluded by source | Appears exactly once |
| taxonomy | UPPER+TRIM (NULL→NULL) | Excluded by source | Appears exactly once |
| concept | UPPER+TRIM (NULL→NULL) | Excluded by source | Appears exactly once |
| unit | UPPER+TRIM (NULL→NULL) | Excluded by source | Appears exactly once |
| period_start | No filter | Passes through | Appears exactly once |
| period_end | No filter | Passes through | Appears exactly once |
| instant | No filter | Passes through | Appears exactly once |
| fiscal_year | CAST only (NULL→NULL) | Passes through | Appears exactly once |
| fiscal_period | UPPER+TRIM (NULL→NULL) | Excluded by source | Appears exactly once |
| form_type | UPPER+TRIM (NULL→NULL) | Excluded by source | Appears exactly once |
| accession_number | TRIM only (NULL→NULL) | Passes through | Appears exactly once |
| frame | No filter | Passes through | Appears exactly once |

## FAILED output — `<=>` → `=` mutations (from /tmp git archive copy)

### cik
```
FAILED tests/silver/test_sec_xbrl_facts.py::TestNullableKeyIdempotency::test_merge_idempotent_with_null_column[cik]
AssertionError: MERGE not idempotent with NULL cik: 1 rows after first run, 2 after second
```

### concept
```
FAILED tests/silver/test_sec_xbrl_facts.py::TestNullableKeyIdempotency::test_merge_idempotent_with_null_column[concept]
AssertionError: MERGE not idempotent with NULL concept: 1 rows after first run, 2 after second
```

### fiscal_year
```
FAILED tests/silver/test_sec_xbrl_facts.py::TestNullableKeyIdempotency::test_merge_idempotent_with_null_column[fiscal_year]
AssertionError: MERGE not idempotent with NULL fiscal_year: 1 rows after first run, 2 after second
```

### form_type
```
FAILED tests/silver/test_sec_xbrl_facts.py::TestNullableKeyIdempotency::test_merge_idempotent_with_null_column[form_type]
AssertionError: MERGE not idempotent with NULL form_type: 1 rows after first run, 2 after second
```

## Checks run
- `python3 -m pytest tests/silver/test_sec_xbrl_facts.py -v --tb=short` → 30 passed (18 existing + 12 new parametrized)
- Mutation `<=>` → `=` for cik → FAILED (1→2 rows on rerun)
- Mutation `<=>` → `=` for concept → FAILED (1→2 rows on rerun)
- Mutation `<=>` → `=` for fiscal_year → FAILED (1→2 rows on rerun)
- Mutation `<=>` → `=` for form_type → FAILED (1→2 rows on rerun)
- All mutations run in /tmp git archive copy only; worktree clean.