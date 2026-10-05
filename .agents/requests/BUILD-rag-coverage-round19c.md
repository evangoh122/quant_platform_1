# BUILD: rag-coverage round 19c (fixes for DeepSeek CHANGES_REQUESTED on rounds 19+19b)

Branch: `slice/rag-coverage` (worktree qp1-ragcov). Commit on THIS branch only; do not create new branches.
Full findings: `.agents/deepseek/VERDICT-rag-coverage-round19.md` — read it first.

## Blocking 1 — store/fetch override-group filings under the filer CIK in the accession
`pipelines/sec_rag_ingest.py` ~1535–1586, 1552, 1718, 1729, 1173: in the anti-join, the first CIK of an
override group (XOM: 0002115436) claims every deduped filing, including legacy `0000034088-…` accessions.
`_accession_filer_cik(dashed)` at :1552 is computed and discarded.
- When a ticker belongs to a CIK override group, plan each filing with the CIK taken from its accession prefix
  (only when that prefix CIK is a member of the group; otherwise keep the iteration CIK and log it).
- Iterate each ticker's deduped filing list ONCE (not once per group CIK) so counters are right:
  `discovered_count` = deduped count; `planned + skipped_existing + failed == discovered` must hold.
- Fetch URL (`data/{int(cik)}/…`), stored `cik`, and `filing_url` must all use that filer CIK.
- Tests (must fail on current HEAD): a planning-level test with an XOM-like group and mixed accession prefixes
  asserting each planned tuple's CIK equals the accession-prefix CIK and the fetch URL uses it; a counter test
  asserting discovered=8, planned=7, skipped=2 for the verdict's scenario (1 holdings + 8 legacy, 1 shared accession,
  1 already-present).

## Blocking 2 — parameterize `repair_cik_ownership` SQL (:1850–1893)
No f-string interpolation of `--tickers`, CIKs or accessions. Use Spark SQL parameter markers
(`spark.sql(query, args={...})` named params) for all values; catalog/schema identifiers may stay as validated
identifiers like the existing adapters. Validate tickers against `^[A-Z][A-Z0-9.\-]{0,9}$` and reject others.
UPDATE must also constrain `ticker` and must refuse to set a CIK outside the ticker's override group.
Remove the dead `group_map` (or use it for the group check above).
- Unit tests with a fake spark: dry-run writes nothing; idempotent (no UPDATE when current == correct);
  a ticker containing `'` is rejected; the UPDATE call carries values as params (assert no ticker/CIK literal
  in the SQL text); a non-group target CIK is refused.

## Also
Replace the two fake "mutation" tests in r19b (`test_mutation_drop_group_check_fails`,
`test_mutation_re_raise_instead_of_record_fails`) with nothing (the real guards already exist) or with real assertions.

## Acceptance
`python -m pytest tests/rag tests/bronze -q` green. Report the new test names and, for each, the mutation of the
source that makes it fail. Do not touch default forms (10-K,10-Q). Do not run anything against Databricks.
