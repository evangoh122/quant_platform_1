# VERDICT: corporate-actions-round7 — MiMo
**Status:** APPROVED
**Round:** 7

## Summary
Massive-only corporate actions pipeline. Removed all yfinance dual-source logic from ETL, notebook, silver SQL, tests, and docs.

## Files modified (7)
- `etl/corporate_actions.py` — removed YFinanceCorporateActionsSource (150 lines), kept protocol + MassiveCorporateActionsSource
- `notebooks/refresh_bronze_corporate_actions.py` — VALID_SOURCES={'massive'}, removed yfinance/both modes, simplified adapter + checkpoint
- `silver/08_silver_ohlcv_day_adjusted.sql` — replaced _resolved_splits + _split_source_mismatches with _massive_splits CTE
- `tests/bronze/test_corporate_actions.py` — removed yfinance-specific tests, updated all source refs to 'massive'
- `tests/silver/test_ohlcv_day_adjusted.py` — removed dual-source CTE tests, added massive-only CTE tests
- `tests/silver/test_silver_sql_semantics.py` — complete rewrite: massive-only DuckDB tests with mutation proofs
- `docs/DATA_SCHEMAS.md` — massive-only source documentation, removed dual-source precedence

## Tests run
```
python -m pytest -q tests/bronze tests/silver tests/test_security.py --ignore=tests/bronze/test_refresh_bronze_cot.py --timeout=60
→ 291 passed, 13 skipped, 0 failed in 11.70s
```

Pre-existing skips: 13 (DuckDB/db.database removed tests, not related to this change).
Pre-existing failures excluded: 5 in `test_refresh_bronze_cot.py::TestComputeReleaseTs` (Databricks connection required, don't touch).

## Removed tests (yfinance dual-source only)
| Test name | Why removed |
|:---|:---|
| `TestSourceProtocol::test_yfinance_source_satisfies_protocol` | YFinanceCorporateActionsSource removed |
| `TestYFinanceNormalization` (entire class, 9 tests) | YFinanceCorporateActionsSource removed |
| `TestRetryBehavior` (entire class, 3 tests) | YFinanceCorporateActionsSource removed |
| `TestResumePerSource` (entire class, 4 tests) | 'both' mode removed; replaced with TestResumeCheckpoint |
| `TestSameDayBothSources::test_same_day_both_sources_factor_20` | Dual-source scenario no longer exists |
| `TestNearDateSuppression::test_near_date_suppression_factor_20` | ±3-day suppression removed (massive-only) |
| `TestYFinanceOnlySplit::test_yfinance_only_applied_once` | yfinance-only scenario no longer exists |
| `TestRatioDisagreement::test_massive_ratio_wins_on_disagreement` | Dual-source ratio disagreement no longer exists |
| `TestMutationProofs::test_mutation_near_match_suppression_removal_fails` | ±3-day suppression removed |
| `TestApplyOnceSemantics::test_dual_source_same_split_one_effect` | Dual-source scenario removed |
| `TestApplyOnceSemantics::test_source_mismatch_ratio_deviation` | Source mismatch no longer exists |
| `TestResolvedSplits` (7 tests) | CTE renamed to _massive_splits, tests rewritten |
| `TestSQLContract::test_sql_has_source_mismatch_detection` | _split_source_mismatches removed |
| `TestSQLContract::test_sql_merges_source_mismatches_to_breaks` | Source mismatch merge removed |
| `TestSQLContract::test_sql_source_mismatch_not_masked` | Source mismatch classification removed |

## Mutation proofs (new)
1. **Dedupe removal → FAILS**: Removing WHERE rn=1 from _massive_splits with duplicate rows → factor ~400 instead of 20
2. **Source filter drop → FAILS**: Removing WHERE source='massive' lets yfinance rows through (documented risk)

## Key-leak tests
- API key redaction in error messages: PASS (SECRET123 never surfaces)
- Exception chain inspection: PASS (__cause__/__context__ clean)
- Notebook _redact_api_key: PASS

## Non-blocking notes
- yfinance remains in requirements.txt (used by etl/extract_yfinance.py for bars/indices)
- The ±3-day near-match suppression is no longer needed since only massive is the source
- SPLIT_SOURCE_MISMATCH and SPLIT_SINGLE_SOURCE classifications no longer emitted; existing rows in data_quality_breaks with these classifications are preserved (not deleted)